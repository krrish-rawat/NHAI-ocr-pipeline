import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.services.llm_client import GeminiExtractionClient, build_response_schema
from src.services.pdf_renderer import PdfRenderer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# source_meta schema
# ---------------------------------------------------------------------------

@dataclass
class SourceMeta:
    """Schema for a single field's provenance metadata.

    bbox        – tightest bounding box covering the matched source_text phrase,
                  in PDF point coordinates (72 pt = 1 inch): [x0, y0, x1, y1].
                  None when OCR data is unavailable or matching failed.

    bbox_lines  – one [x0, y0, x1, y1] per *line* of text within the match
                  (useful when source_text spans multiple lines).
                  None when bbox is None.

    Coordinates are zoom-independent PDF points, not raw Tesseract pixels.
    pageNumber is 1-based (0 means no OCR match was found).
    """
    pageNumber: int = 0
    text: str = "Null"
    confidence: str = "unknown"
    bbox: list[int] | None = None
    bbox_lines: list[list[int]] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "pageNumber": self.pageNumber,
            "text": self.text,
            "confidence": self.confidence,
        }
        if self.bbox is not None:
            d["bbox"] = self.bbox
        if self.bbox_lines is not None:
            d["bbox_lines"] = self.bbox_lines
        return d


# ---------------------------------------------------------------------------
# OCR cache — one index per document, populated once at upload time
# ---------------------------------------------------------------------------

@dataclass
class OcrIndexEntry:
    """Bundles the per-page word list with the zoom factor used during render.

    Storing zoom here means the bbox converter never has to reach back into
    the renderer — the information travels with the data.

    pages:  one list of word-dicts per rendered page
              {"text": str, "left": int, "top": int,
               "width": int, "height": int, "confidence": float}
    zoom:   PdfRenderer.zoom value that was active when the page was rasterised
    """
    pages: list[list[dict[str, Any]]]
    zoom: float


# Public alias used throughout the module
OcrIndex = OcrIndexEntry


@dataclass
class OcrCache:
    """In-process cache: stores one OcrIndexEntry per uploaded document.

    Keyed by absolute temp-file path.  A fixed capacity cap (64 entries)
    prevents unbounded growth under concurrent load; eviction is FIFO because
    temp files are deleted after every request anyway.
    """
    _store: dict[str, OcrIndex] = field(default_factory=dict, repr=False)
    _max_entries: int = 64

    def get(self, pdf_path: str) -> OcrIndex | None:
        return self._store.get(pdf_path)

    def put(self, pdf_path: str, index: OcrIndex) -> None:
        if len(self._store) >= self._max_entries:
            # Evict the oldest entry (insertion-ordered dict, Python 3.7+).
            self._store.pop(next(iter(self._store)))
        self._store[pdf_path] = index

    def evict(self, pdf_path: str) -> None:
        self._store.pop(pdf_path, None)


# Module-level singleton — shared across all ExtractionService instances.
_ocr_cache = OcrCache()


# ---------------------------------------------------------------------------
# Text normalisation (shared by grounding check and bbox matcher)
# ---------------------------------------------------------------------------

def _normalize_for_grounding(text: str) -> str:
    """Collapse whitespace and lower-case for fuzzy comparisons."""
    return re.sub(r"\s+", " ", text.strip()).lower()


# ---------------------------------------------------------------------------
# Fuzzy matching + coordinate-space conversion
# ---------------------------------------------------------------------------

# Minimum rapidfuzz / difflib score (0-100) for a candidate window to be
# accepted as a match.  85 ≈ 85 % character overlap.
_FUZZY_THRESHOLD = 85.0


def _fuzzy_available() -> bool:
    """Return True if rapidfuzz is importable (optional C-extension speedup)."""
    try:
        import rapidfuzz  # noqa: F401
        return True
    except ImportError:
        return False


def _score_window(query_norm: str, window_words: list[dict[str, Any]]) -> float:
    """Similarity score between *query_norm* and a consecutive word window.

    Uses ``rapidfuzz.fuzz.partial_ratio`` when available (faster, C extension),
    otherwise falls back to ``difflib.SequenceMatcher``.  Both return a 0-100
    value representing the percentage of characters that match.
    """
    window_text = " ".join(_normalize_for_grounding(w["text"]) for w in window_words)
    if _fuzzy_available():
        from rapidfuzz import fuzz
        return fuzz.partial_ratio(query_norm, window_text)
    import difflib
    return difflib.SequenceMatcher(None, query_norm, window_text).ratio() * 100.0


def _pixels_to_points(coords: list[float], zoom: float) -> list[float]:
    """Convert Tesseract pixel coordinates to zoom-independent PDF points.

    Tesseract operates on the rendered bitmap which was produced at
    ``zoom × 72 DPI``.  Dividing each coordinate by *zoom* recovers the
    original PDF point space (1 pt = 1/72 inch), making the values
    independent of the zoom level chosen at render time.

    Parameters
    ----------
    coords:
        ``[x0, y0, x1, y1]`` in pixel space.
    zoom:
        The zoom factor used when rendering the page (``PdfRenderer.zoom``).

    Returns
    -------
    list[float]
        ``[x0_pt, y0_pt, x1_pt, y1_pt]`` rounded to two decimal places.
    """
    return [round(c / zoom, 2) for c in coords]


def _words_to_bbox_pts(words: list[dict[str, Any]], zoom: float) -> list[float]:
    """Union bounding box of *words* converted to PDF points."""
    x0 = min(w["left"] for w in words)
    y0 = min(w["top"] for w in words)
    x1 = max(w["left"] + w["width"] for w in words)
    y1 = max(w["top"] + w["height"] for w in words)
    return _pixels_to_points([x0, y0, x1, y1], zoom)


def _group_into_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group *words* into visual lines using y-axis proximity.

    Words are sorted top-to-bottom then left-to-right.  A new line begins
    when the vertical gap to the previous word exceeds half the average
    height of the two adjacent words — robust for standard body text.
    """
    sorted_words = sorted(words, key=lambda w: (w["top"], w["left"]))
    lines: list[list[dict[str, Any]]] = [[sorted_words[0]]]
    for word in sorted_words[1:]:
        prev = lines[-1][-1]
        avg_h = (prev["height"] + word["height"]) / 2.0
        if abs(word["top"] - prev["top"]) > avg_h * 0.5:
            lines.append([word])
        else:
            lines[-1].append(word)
    return lines


def _build_bbox_for_source_text(
    source_text: str,
    ocr_index: OcrIndex,
) -> tuple[int, list[float] | None, list[list[float]] | None]:
    """Map *source_text* onto the OCR word index and return PDF-point bboxes.

    Algorithm
    ---------
    1. Normalise the query string.
    2. For every page, slide a window of ``len(query_tokens)`` words and score
       it with rapidfuzz (or difflib as fallback).
    3. Accept the highest-scoring window that clears ``_FUZZY_THRESHOLD`` (85).
    4. If no full-length window qualifies, try shrinking the window down to
       ``max(1, len-2)`` words to survive minor OCR omissions.
    5. Convert matched pixel coordinates to PDF points by dividing by zoom.
    6. Group matched words into lines; emit ``bbox_lines`` only when there are
       two or more lines (single-line matches carry only ``bbox``).
    7. On any failure return ``(0, None, None)`` — callers omit the fields.

    Parameters
    ----------
    source_text:
        The verbatim (or near-verbatim) phrase returned by Gemini.
    ocr_index:
        Cached ``OcrIndexEntry`` carrying per-page word lists and the zoom
        factor used at render time.

    Returns
    -------
    tuple[int, list[float] | None, list[list[float]] | None]
        ``(page_number, bbox, bbox_lines)`` where *page_number* is 1-based
        (0 means no match), coordinates in PDF points, or ``(0, None, None)``.
    """
    # --- guard clauses --------------------------------------------------
    if not ocr_index or not ocr_index.pages:
        return 0, None, None
    if not source_text or source_text.strip().lower() in ("null", ""):
        return 0, None, None

    query_norm = _normalize_for_grounding(source_text)
    query_tokens = query_norm.split()
    if not query_tokens:
        return 0, None, None

    zoom = ocr_index.zoom
    best_words: list[dict[str, Any]] = []
    best_score: float = 0.0
    best_page: int = 0  # 1-based page number of the best match

    # --- sliding-window fuzzy search ------------------------------------
    # Shrink window by up to 2 words to survive minor OCR omissions.
    min_window = max(1, len(query_tokens) - 2)

    for page_idx, page_words in enumerate(ocr_index.pages):
        if not page_words:
            continue

        page_best_words: list[dict[str, Any]] = []
        page_best_score: float = 0.0

        for win_size in range(len(query_tokens), min_window - 1, -1):
            for start in range(len(page_words) - win_size + 1):
                window = page_words[start : start + win_size]
                score = _score_window(query_norm, window)
                if score > page_best_score:
                    page_best_score = score
                    page_best_words = window
                if page_best_score >= 99.0:
                    break
            if page_best_score >= 99.0:
                break

        if page_best_score > best_score:
            best_score = page_best_score
            best_words = page_best_words
            best_page  = page_idx + 1  # convert to 1-based

        if best_score >= _FUZZY_THRESHOLD:
            break  # good enough — stop scanning further pages

    # --- threshold gate -------------------------------------------------
    if best_score < _FUZZY_THRESHOLD or not best_words:
        logger.debug(
            "Fuzzy match below threshold (score=%.1f < %.1f) for: %.80r",
            best_score, _FUZZY_THRESHOLD, source_text,
        )
        return 0, None, None

    logger.debug(
        "Fuzzy match score=%.1f page=%d for: %.80r", best_score, best_page, source_text
    )

    # --- coordinate conversion ------------------------------------------
    bbox = _words_to_bbox_pts(best_words, zoom)

    lines = _group_into_lines(best_words)
    bbox_lines: list[list[float]] | None = (
        [_words_to_bbox_pts(ln, zoom) for ln in lines]
        if len(lines) > 1
        else None
    )

    return best_page, bbox, bbox_lines


# ---------------------------------------------------------------------------
# Attribute normalisation & prompts
# ---------------------------------------------------------------------------

# Classification prompt for TEXT-based input (Mistral OCR structured text)
CLASSIFICATION_PROMPT_TEXT = """
You are analyzing structured OCR text extracted from a government document.
Your ONLY task is to classify the document type.

The full document text (structured OCR text) is provided above. Examine it carefully and identify which type it is.

Choose EXACTLY ONE from this list:
- "letter of award (loa)" - if this is a contract award letter
- "completion certificate (cc)" - if this is a completion certificate (not provisional)
- "provisional completion certificate (pcc)" - if this is a provisional completion certificate
- "financial closure" - if this is a financial closure document
- "debarment records" - if this is a debarment, blacklisting, or restriction from participation document
- "other" - if it does not match any of the above types

Return ONLY the classification string, nothing else. No explanation, no JSON, just the type string.

Examples:
- If you see "Letter of Award" or "LOA" in the text → return "letter of award (loa)"
- If you see "Completion Certificate" with "Provisional" → return "provisional completion certificate (pcc)"
- If you see "Completion Certificate" without "Provisional" → return "completion certificate (cc)"
- If you see "Financial Closure" → return "financial closure"
- If you see "Restriction for Participation", "Debarment", "Blacklisted", or "not allowed to participate" → return "debarment records"
- If it's an invoice, purchase order, or other document → return "other"
"""


def normalize_attributes(raw_attributes: str | list[str]) -> list[str]:
    if isinstance(raw_attributes, str):
        parts = re.split(r"[\n,]+", raw_attributes)
    else:
        parts = raw_attributes

    attributes: list[str] = []
    seen: set[str] = set()

    for part in parts:
        cleaned = re.sub(r"\s+", " ", str(part).strip())
        if not cleaned:
            continue

        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            attributes.append(cleaned)

    return attributes


def build_dynamic_prompt(attributes: list[str]) -> str:
    """Build extraction prompt for IMAGE-based input (fallback path)."""
    fields = "\n".join(f"- {attribute}" for attribute in attributes)

    return f"""
You are a precise data extractor for official government PDF documents.
The PDF pages are provided as images and may contain English, Hindi, tables, merged cells, scanned text, or appended letters.

═══════════════════════════════════════════════════
STRICT GROUNDING RULES — READ CAREFULLY
═══════════════════════════════════════════════════
1. Extract ONLY values that are explicitly and unambiguously stated in the document.
   Do NOT infer, calculate, estimate, or supply values from outside knowledge.

2. This document may contain many similar values (e.g. 7+ distinct dates, multiple
   names, several amounts). You MUST match each field strictly to the sentence or
   clause that explicitly labels it. The label in the document must directly name
   or describe that field — do NOT borrow a value from a different clause even if
   the value looks plausible.
   Examples of incorrect attribution:
   - Using an EOT date, completion date, or notice-to-proceed date for "Agreement Made Date"
   - Using a work-order date for "Contract Award Date"
   - Using one party's name for another party's field
   Always ask: "Does the document text itself say this value belongs to this field?"

3. For every extracted field you MUST return the shortest exact phrase or sentence
   from the PDF that directly states the value AND names the field — this is the
   source_text. The source_text must be verbatim or near-verbatim from the document.
   It will be searched and highlighted in the original PDF, so accuracy is critical.

4. If no explicit statement in the document supports a field, return:
   value: "Null"
   source_text: "Null"
   Never fabricate a plausible-looking value. If you are uncertain, return Null.

5. Dates: preserve the format exactly as written unless the intended format is
   unambiguous (e.g. "23rd March 2021" → "2021-03-23" is acceptable; otherwise
   return as written). For compound date values (e.g. "13.03.2025 & 02.07.2025"),
   return the full compound string exactly as it appears.

6. Multiple records: if a table lists multiple people/entities/rows, return one
   record object per row. Apply shared header context (headings, merged cells) to
   every row.
═══════════════════════════════════════════════════

Extract the following fields:
{fields}

Additionally, classify the type of document being analyzed. Choose EXACTLY ONE from this list:
- "letter of award (loa)"
- "completion certificate (cc)"
- "provisional completion certificate (pcc)"
- "financial closure"
- "debarment records"
- "other"

Return strict JSON only, with this exact shape:
{{
  "document_type": "your classification here (one of the 6 types above)",
  "records": [
    {{
      "attribute_name": {{
        "value": "extracted value or Null",
        "source_text": "verbatim phrase from document that states this value, or Null"
      }}
    }}
  ]
}}

The document_type must appear at the root level of the JSON (sibling to "records").
Every attribute key must appear in every record. Do not add any keys outside "document_type" and "records".
Do not include markdown, explanations, or comments.
"""


def build_dynamic_prompt_text(attributes: list[str]) -> str:
    """Build extraction prompt for TEXT-based input (Mistral OCR structured text).
    
    This variant is identical to build_dynamic_prompt but adapted for structured
    OCR text instead of images, while maintaining all grounding rules.
    """
    fields = "\n".join(f"- {attribute}" for attribute in attributes)

    return f"""
You are a precise data extractor for official government documents.
The structured OCR text extracted from the document is provided above. The document may contain English, Hindi, tables, merged cells, scanned content, or appended letters.

═══════════════════════════════════════════════════
STRICT GROUNDING RULES — READ CAREFULLY
═══════════════════════════════════════════════════
1. Extract ONLY values that are explicitly and unambiguously stated in the structured OCR text above.
   Do NOT infer, calculate, estimate, or supply values from outside knowledge.

2. This document may contain many similar values (e.g. 7+ distinct dates, multiple
   names, several amounts). You MUST match each field strictly to the sentence or
   clause in the structured OCR text that explicitly labels it. The label in the text must directly name
   or describe that field — do NOT borrow a value from a different clause even if
   the value looks plausible.
   Examples of incorrect attribution:
   - Using an EOT date, completion date, or notice-to-proceed date for "Agreement Made Date"
   - Using a work-order date for "Contract Award Date"
   - Using one party's name for another party's field
   Always ask: "Does the structured OCR text itself say this value belongs to this field?"

3. For every extracted field you MUST return the shortest exact phrase or sentence
   from the structured OCR text that directly states the value AND names the field — this is the
   source_text. The source_text must be verbatim or near-verbatim from the structured OCR text.
   It will be searched and highlighted in the original PDF, so accuracy is critical.

4. If no explicit statement in the structured OCR text supports a field, return:
   value: "Null"
   source_text: "Null"
   Never fabricate a plausible-looking value. If you are uncertain, return Null.

5. Dates: preserve the format exactly as written in the structured OCR text unless the intended format is
   unambiguous (e.g. "23rd March 2021" → "2021-03-23" is acceptable; otherwise
   return as written). For compound date values (e.g. "13.03.2025 & 02.07.2025"),
   return the full compound string exactly as it appears.

6. Multiple records: if a table in the structured OCR text lists multiple people/entities/rows, return one
   record object per row. Apply shared header context (headings, merged cells) to
   every row.

7. Ground all extracted values against the structured OCR text provided above. Ensure each value
   can be traced back to a specific phrase in that text.
═══════════════════════════════════════════════════

Extract the following fields:
{fields}

Additionally, classify the type of document being analyzed. Choose EXACTLY ONE from this list:
- "letter of award (loa)"
- "completion certificate (cc)"
- "provisional completion certificate (pcc)"
- "financial closure"
- "debarment records"
- "other"

Return strict JSON only, with this exact shape:
{{
  "document_type": "your classification here (one of the 6 types above)",
  "records": [
    {{
      "attribute_name": {{
        "value": "extracted value or Null",
        "source_text": "verbatim phrase from structured OCR text that states this value, or Null"
      }}
    }}
  ]
}}

The document_type must appear at the root level of the JSON (sibling to "records").
Every attribute key must appear in every record. Do not add any keys outside "document_type" and "records".
Do not include markdown, explanations, or comments.
"""


# ---------------------------------------------------------------------------
# Grounding confidence
# ---------------------------------------------------------------------------

def _grounding_check(value: str, source_text: str) -> str:
    """
    Return a confidence level based on whether source_text contains the value.

    Logic:
    - Both Null           → "unknown" (not a hallucination, just missing)
    - value is Null       → "unknown"
    - source_text is Null → "low"   (model produced a value but no source)
    - value found in source_text → "high"
    - all words of value appear in source_text → "medium" (fragmented text)
    - source_text does not contain value → "low"  (grounding failure)
    """
    v_norm = _normalize_for_grounding(value)
    s_norm = _normalize_for_grounding(source_text)

    if v_norm in ("null", "") and s_norm in ("null", ""):
        return "unknown"
    if v_norm in ("null", ""):
        return "unknown"
    if s_norm in ("null", ""):
        return "low"

    if v_norm in s_norm:
        return "high"

    tokens = [t for t in v_norm.split() if len(t) >= 2]
    if tokens and all(t in s_norm for t in tokens):
        return "medium"

    return "low"


# ---------------------------------------------------------------------------
# Record coercion
# ---------------------------------------------------------------------------

def _coerce_source_meta(
    raw_record: dict[str, Any],
    attributes: list[str],
    ocr_index: OcrIndex | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the source_meta dict, now including optional bbox fields.

    When *ocr_index* is supplied the function searches it for each
    source_text phrase and attaches pixel-space bounding boxes.
    """
    source_meta: dict[str, dict[str, Any]] = {}

    for attribute in attributes:
        field_data = raw_record.get(attribute, {})

        if isinstance(field_data, dict):
            value       = str(field_data.get("value")       or "Null").strip() or "Null"
            source_text = str(field_data.get("source_text") or "Null").strip() or "Null"
        else:
            value       = str(field_data).strip() or "Null"
            source_text = "Null"

        confidence = _grounding_check(value, source_text)

        page_number: int = 0
        bbox: list[float] | None = None
        bbox_lines: list[list[float]] | None = None

        if ocr_index:
            page_number, bbox, bbox_lines = _build_bbox_for_source_text(source_text, ocr_index)

        meta = SourceMeta(
            pageNumber=page_number,
            text=source_text,
            confidence=confidence,
            bbox=bbox,
            bbox_lines=bbox_lines,
        )
        source_meta[attribute] = meta.to_dict()

    return source_meta


def _coerce_records(
    data: dict[str, Any],
    attributes: list[str],
    ocr_index: OcrIndex | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Extract records and document_type from LLM response.
    
    Returns:
        (document_type, records) where document_type is the classification string
        and records is the list of extracted record dictionaries.
    """
    raw_records = data.get("records", [])
    if not isinstance(raw_records, list):
        raw_records = []

    # Extract document classification (default to "other" if missing)
    document_type = str(data.get("document_type", "other")).strip() or "other"

    records: list[dict[str, Any]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue

        record: dict[str, Any] = {}
        for attribute in attributes:
            field_data = raw_record.get(attribute, {})

            if isinstance(field_data, dict):
                value = str(field_data.get("value") or "Null").strip() or "Null"
            else:
                value = str(field_data).strip() or "Null"

            if value == "":
                value = "Null"
            record[attribute] = value

        record["source_meta"] = _coerce_source_meta(raw_record, attributes, ocr_index)
        records.append(record)

    return document_type, records


def _friendly_error(exc: Exception) -> str:
    error_text = str(exc)
    if "429" in error_text or "ResourceExhausted" in error_text:
        return "API Rate Limit Exceeded (429). Try fewer files at a time."
    return error_text


# ---------------------------------------------------------------------------
# Document type validation
# ---------------------------------------------------------------------------

# All accepted abbreviations and keywords — any match is sufficient.
# Ordered from most specific to least to avoid false positives.
_ACCEPTED_DOC_PATTERNS: list[str] = [
    # Full phrases (from Gemini's constrained output)
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
    "debarment records",
    "debarment of individuals",
    "restriction for participation",
    "blacklisting",
    "blacklisted",
    # Abbreviated / partial
    "letter of award",
    "financial closure",
    "provisional completion certificate",
    "provisional completion",
    "completion certificate",
    "provisional cc",
    "provisional pcc",
    "debarment",
    "restriction",
]

# Single-word tokens that are unambiguously valid when standalone
_ACCEPTED_DOC_TOKENS: frozenset[str] = frozenset(["loa", "cc", "pcc", "debarment", "restriction", "blacklisting"])


def _is_accepted_doc_type(raw_type: str) -> bool:
    """Return True if *raw_type* matches any accepted NHAI document type.

    Handles:
      • Full phrases returned by Gemini (constrained output)
      • Common abbreviations (LOA, CC, PCC)
      • Partial phrases / mixed casing
      • Trailing words like "document", "form", etc.
    """
    if not raw_type:
        return False

    normalized = raw_type.lower().strip()

    # Exact or substring match against all accepted patterns
    if any(pattern in normalized for pattern in _ACCEPTED_DOC_PATTERNS):
        return True

    # Token-level check: "pcc document", "loa form", etc.
    tokens = set(normalized.split())
    if tokens & _ACCEPTED_DOC_TOKENS:
        return True

    return False

@dataclass
class ExtractionService:
    renderer: PdfRenderer
    llm_client: GeminiExtractionClient
    mistral_ocr: Any = None  # MistralOcrClient | None — None means feature off

    # ------------------------------------------------------------------
    # Internal: OCR index (run once per document at ingestion time)
    # ------------------------------------------------------------------

    def _get_or_build_ocr_index(self, pdf_path: str) -> OcrIndex:
        """Return the cached OCR index for *pdf_path*, building it if needed.

        The index is stored in the module-level *_ocr_cache* so it survives
        across multiple attribute-extraction calls on the same document within
        a single request, but is automatically evicted after the temp file is
        deleted by the caller.
        """
        cached = _ocr_cache.get(pdf_path)
        if cached is not None:
            return cached

        # Run OCR once — this is the only place it ever executes per document.
        pages = self.renderer.extract_words_from_pdf(pdf_path)
        index = OcrIndexEntry(pages=pages, zoom=self.renderer.zoom)
        _ocr_cache.put(pdf_path, index)
        return index

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_document(
        self,
        pdf_path: str,
        text_context: str | None = None,
    ) -> str:
        """Quick document classification without field extraction.
        
        This is a lightweight operation that only asks Gemini to identify
        the document type. Much faster and cheaper than full extraction.
        
        When text_context is provided (Mistral OCR path), sends text only.
        Otherwise falls back to image-based classification.
        
        Returns:
            Document type string (e.g., "letter of award (loa)", "invoice", "other")
        """
        try:
            if text_context:
                # Text-based classification (fast — no image upload)
                doc_type = self.llm_client.generate_text(
                    CLASSIFICATION_PROMPT_TEXT, text_context=text_context
                )
            else:
                # Image-based classification (fallback)
                images = self.renderer.render_to_images(pdf_path)
                
                # Lightweight classification-only prompt
                prompt = """
You are analyzing a government document image. Your ONLY task is to classify the document type.

Examine the document carefully and identify which type it is. Choose EXACTLY ONE from this list:
- "letter of award (loa)" - if this is a contract award letter
- "completion certificate (cc)" - if this is a completion certificate (not provisional)
- "provisional completion certificate (pcc)" - if this is a provisional completion certificate
- "financial closure" - if this is a financial closure document
- "debarment records" - if this is a debarment, blacklisting, or restriction from participation document
- "other" - if it does not match any of the above types

Return ONLY the classification string, nothing else. No explanation, no JSON, just the type string.

Examples:
- If you see "Letter of Award" or "LOA" in the header → return "letter of award (loa)"
- If you see "Completion Certificate" with "Provisional" → return "provisional completion certificate (pcc)"
- If you see "Completion Certificate" without "Provisional" → return "completion certificate (cc)"
- If you see "Financial Closure" → return "financial closure"
- If you see "Restriction for Participation", "Debarment", "Blacklisted", or "not allowed to participate" → return "debarment records"
- If it's an invoice, purchase order, or other document → return "other"
"""
                doc_type = self.llm_client.generate_text(prompt, images)
            
            return doc_type.strip().lower()
        except Exception as exc:
            logger.error(f"Document classification failed: {exc}")
            return "other"  # Fail-safe: treat as invalid

    def extract_from_pdf(
        self,
        pdf_path: str,
        attributes: list[str],
        ocr_index: OcrIndex | None = None,
        text_context: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Extract records and document type from PDF.
        
        When text_context is provided (Mistral OCR path), sends text only.
        Otherwise falls back to image-based extraction.
        
        Returns:
            (document_type, records) tuple.
        """
        if not attributes:
            raise ValueError("At least one extraction attribute is required.")

        if text_context:
            # Text-based extraction (fast — no image upload)
            prompt = build_dynamic_prompt_text(attributes)
            schema = build_response_schema(attributes)
            data = self.llm_client.generate_json(prompt, text_context=text_context, response_schema=schema)
        else:
            # Image-based extraction (fallback)
            images = self.renderer.render_to_images(pdf_path)
            prompt = build_dynamic_prompt(attributes)
            schema = build_response_schema(attributes)
            data = self.llm_client.generate_json(prompt, images, response_schema=schema)

        document_type, records = _coerce_records(data, attributes, ocr_index)

        if not records:
            raise ValueError("Model returned no records for this document.")

        return document_type, records

    def extract_file_records(
        self,
        pdf_path: str,
        source_file: str,
        attributes: list[str],
        skip_validation: bool = False,
    ) -> dict[str, Any]:
        """Full ingestion pipeline for one document with PRE-EXTRACTION validation.

        PHASE 0: Mistral OCR (if configured) — extract structured text once
        PHASE 1: Quick document classification (fast, lightweight) — skipped if skip_validation=True
        PHASE 2: Only runs full extraction if Phase 1 passes validation
        
        This saves time and API costs by aborting early for invalid documents.
        Falls back to image-based pipeline if Mistral OCR fails or returns <50 chars.
        
        Returns:
            Dictionary with "records" (list) and "document_validity" (dict).
        """
        try:
            # ═══════════════════════════════════════════════════════════════
            # PHASE 0: MISTRAL OCR (once for entire request)
            # ═══════════════════════════════════════════════════════════════
            structured_text: str | None = None
            if self.mistral_ocr is not None:
                try:
                    structured_text = self.mistral_ocr.extract_text(pdf_path)
                    if len(structured_text) < 50:
                        logger.warning(
                            "Mistral OCR returned only %d chars, falling back to images",
                            len(structured_text),
                        )
                        structured_text = None
                except Exception as exc:
                    logger.warning(
                        "Mistral OCR failed (%s: %s), falling back to images",
                        type(exc).__name__,
                        exc,
                    )
                    structured_text = None

            # ═══════════════════════════════════════════════════════════════
            # PHASE 1: QUICK CLASSIFICATION (Pre-Extraction Gate)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE 1 START: Classifying document: {source_file}")
            logger.info(f"{'='*70}\n")
            
            if skip_validation:
                logger.info("Phase 1 SKIPPED (skip_validation=True)")
                document_type = "forced extraction"
                is_valid = True
            else:
                document_type = self.classify_document(pdf_path, text_context=structured_text)
                is_valid = _is_accepted_doc_type(document_type)
            
            logger.info(f"\n>>> Phase 1 Classification Result <<<")
            logger.info(f"  Document Type: '{document_type}'")
            logger.info(f"  Is Valid: {is_valid}")
            logger.info(f"  OCR Path: {'Mistral text' if structured_text else 'Images'}\n")
            
            # BUILD EARLY ABORT RESPONSE if invalid
            if not is_valid:
                logger.warning(f"\n{'='*70}")
                logger.warning(f"PHASE 1 BLOCKED: Document rejected")
                logger.warning(f"  Type: '{document_type}' not in accepted types")
                logger.warning(f"  Blocking extraction and returning validation error")
                logger.warning(f"{'='*70}\n")
                
                return {
                    "records": [
                        {
                            "source_file": source_file,
                            **{attribute: "Null" for attribute in attributes},
                            "source_meta": {
                                attribute: SourceMeta(
                                    pageNumber=0, text="Null", confidence="unknown"
                                ).to_dict()
                                for attribute in attributes
                            },
                            "status": "Blocked",
                            "failure_reason": f"Invalid document type: {document_type}",
                        }
                    ],
                    "document_validity": {
                        "is_valid": False,
                        "detected_type": document_type,
                        "confidence": "high",
                        "message": None,
                    },
                }
            
            # ═══════════════════════════════════════════════════════════════
            # PHASE 2: FULL EXTRACTION (Only if Phase 1 passed)
            # ═══════════════════════════════════════════════════════════════
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE 2 START: Document validated, proceeding with extraction")
            logger.info(f"  Path: {'Mistral text' if structured_text else 'Images (fallback)'}")
            logger.info(f"{'='*70}\n")
            
            # ① Run Tesseract OCR for bbox/source_meta only on image fallback path.
            # When Mistral OCR provides structured text, skip Tesseract to save ~3s.
            ocr_index = None
            if not structured_text:
                ocr_index = self._get_or_build_ocr_index(pdf_path)

            # ② LLM extraction — uses text_context when available, images otherwise
            extraction_doc_type, records = self.extract_from_pdf(
                pdf_path, attributes, ocr_index, text_context=structured_text
            )
            
            # Use the quick classification result for consistency
            document_validity = {
                "is_valid": True,
                "detected_type": document_type,  # Use Phase 1 classification
                "confidence": "high",
                "message": None,
            }

            # ③ Attach metadata to records
            enriched_records = [
                {
                    "source_file": source_file,
                    **record,
                    "status": "Success",
                    "failure_reason": "",
                }
                for record in records
            ]

            return {
                "records": enriched_records,
                "document_validity": document_validity,
            }

        except Exception as exc:
            logger.error(f"Extraction failed for {source_file}: {exc}")
            return {
                "records": [
                    {
                        "source_file": source_file,
                        **{attribute: "Null" for attribute in attributes},
                        "source_meta": {
                            attribute: SourceMeta(
                                pageNumber=0, text="Null", confidence="unknown"
                            ).to_dict()
                            for attribute in attributes
                        },
                        "status": "Failed",
                        "failure_reason": _friendly_error(exc),
                    }
                ],
                "document_validity": {
                    "is_valid": False,
                    "detected_type": "Error",
                    "confidence": "high",
                    "message": f"Extraction failed: {_friendly_error(exc)}",
                },
            }
        finally:
            # ④ Evict the OCR index now that we're done with this document.
            _ocr_cache.evict(pdf_path)


def build_extraction_service() -> ExtractionService:
    from src.services.settings import settings

    mistral_ocr = None
    if settings.use_mistral_ocr:
        if not settings.mistral_api_key:
            raise ValueError(
                "MISTRAL_API_KEY must be set when USE_MISTRAL_OCR is enabled. "
                "Either set MISTRAL_API_KEY in your environment or set USE_MISTRAL_OCR=false."
            )
        from src.services.mistral_ocr_client import MistralOcrClient
        mistral_ocr = MistralOcrClient(
            api_key=settings.mistral_api_key,
            model=settings.mistral_ocr_model,
        )

    # Use Mistral LLM when configured, otherwise fall back to Gemini
    if settings.use_mistral_llm and settings.mistral_api_key:
        from src.services.mistral_llm_client import MistralLLMClient
        llm_client = MistralLLMClient(
            api_key=settings.mistral_api_key,
            model=settings.mistral_llm_model,
            extraction_model=settings.mistral_extraction_model,
        )
    else:
        llm_client = GeminiExtractionClient()

    return ExtractionService(
        renderer=PdfRenderer(),
        llm_client=llm_client,
        mistral_ocr=mistral_ocr,
    )

# Technical Design: Mistral OCR Pipeline Integration

## Overview

This design replaces the image-heavy Gemini extraction pipeline with a text-first approach: Mistral OCR converts the PDF to structured markdown once, and that text is sent to Gemini for both classification and extraction — eliminating the multi-image payload that causes the current 15–20s latency.

The Tesseract-based bbox pipeline for UI highlighting remains independent and unchanged.

---

## Architecture

### Current Pipeline (Slow Path)

```
PDF Upload
    ↓
PdfRenderer.render_to_images()          ← renders all pages as JPEG (slow)
    ↓
Phase 1: Gemini generate_text(prompt, images[])   ← uploads all images
    ↓
Phase 2: Gemini generate_json(prompt, images[])   ← uploads all images AGAIN
    ↓
PdfRenderer.extract_words_from_pdf()    ← Tesseract OCR for bbox
    ↓
_coerce_source_meta() with OCR_Index
    ↓
Response
```

### New Pipeline (Fast Path)

```
PDF Upload
    ↓
MistralOcrClient.extract_text(pdf_path) ← one API call, returns markdown text
    ↓
Phase 1: Gemini generate_text(prompt, text_context=structured_text)   ← text only, no images
    ↓
Phase 2: Gemini generate_json(prompt, text_context=structured_text)   ← text only, no images
    ↓
PdfRenderer.extract_words_from_pdf()    ← Tesseract OCR for bbox (unchanged)
    ↓
_coerce_source_meta() with OCR_Index    ← unchanged
    ↓
Response
```

### Fallback Path (on Mistral failure)

```
PDF Upload
    ↓
MistralOcrClient.extract_text() → FAILS (timeout, auth, empty text)
    ↓
Log warning, set structured_text = None
    ↓
PdfRenderer.render_to_images()          ← only on fallback
    ↓
Phase 1: Gemini generate_text(prompt, images[])   ← original image path
    ↓
Phase 2: Gemini generate_json(prompt, images[])   ← original image path
    ↓
PdfRenderer.extract_words_from_pdf()    ← Tesseract OCR for bbox
    ↓
_coerce_source_meta() with OCR_Index
    ↓
Response
```

---

## Components and Interfaces

### 1. New File: `src/services/mistral_ocr_client.py`

```python
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 50  # Characters; below this threshold text is considered unusable
_API_TIMEOUT = 8       # Seconds


class MistralOcrClient:
    """Calls the Mistral OCR API to convert a PDF into structured markdown text."""

    def __init__(self, api_key: str, model: str = "mistral-ocr-latest") -> None:
        self.api_key = api_key
        self.model = model

    def extract_text(self, pdf_path: str) -> str:
        """Convert PDF at pdf_path to structured markdown text via Mistral OCR.

        Returns:
            Concatenated structured text for all pages, joined by newlines.

        Raises:
            ImportError: If the mistralai package is not installed.
            TimeoutError: If the API call exceeds 8 seconds.
            Exception: On network/auth/API errors (non-ImportError).
        """
        try:
            from mistralai import Mistral
        except ImportError:
            raise ImportError(
                "The 'mistralai' package is required for Mistral OCR. "
                "Install it with: pip install mistralai"
            )

        client = Mistral(api_key=self.api_key)

        # Upload PDF file to Mistral
        pdf_file = Path(pdf_path)
        with open(pdf_file, "rb") as f:
            uploaded = client.files.upload(
                file={"file_name": pdf_file.name, "content": f},
                purpose="ocr",
            )

        # Get signed URL for the uploaded file
        signed_url = client.files.get_signed_url(file_id=uploaded.id)

        # Call OCR endpoint
        response = client.ocr.process(
            model=self.model,
            document={
                "type": "document_url",
                "document_url": signed_url.url,
            },
        )

        # Concatenate page text
        pages = response.pages or []
        text_parts = [page.markdown for page in pages if page.markdown]
        structured_text = "\n\n".join(text_parts)

        logger.debug(
            "Mistral OCR complete: %d pages, %d characters",
            len(pages),
            len(structured_text),
        )

        return structured_text
```

**Key design decisions:**
- Lazy import of `mistralai` inside method body (app starts without package)
- 8-second timeout enforced via SDK timeout parameter or wrapper
- Returns plain string — all page text joined by double-newline
- Upload → signed URL → OCR process (Mistral's recommended flow)

---

### 2. Modified File: `src/services/settings.py`

```python
@dataclass(frozen=True)
class AppSettings:
    # Existing fields (unchanged)
    model_name: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    extraction_retries: int = int(os.getenv("EXTRACTION_RETRIES", "2"))
    summary_timeout_seconds: int = int(os.getenv("SUMMARY_TIMEOUT_SECONDS", "60"))

    # New fields
    mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
    mistral_ocr_model: str = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
    use_mistral_ocr: bool = bool(os.getenv("USE_MISTRAL_OCR", "") or os.getenv("MISTRAL_API_KEY"))
```

**Logic:** `use_mistral_ocr` defaults to `True` when `MISTRAL_API_KEY` is set (non-empty), `False` otherwise. Can be explicitly set to "0"/"false" to override.

---

### 3. Modified File: `src/services/llm_client.py`

Add `text_context: str | None = None` parameter to both public methods:

```python
class GeminiExtractionClient:

    def generate_json(
        self,
        prompt: str,
        images: list[Image.Image] | None = None,
        retries: int = settings.extraction_retries,
        response_schema: type | None = None,
        text_context: str | None = None,          # ← NEW
    ) -> dict[str, Any]:
        ...
        # Build content array
        if text_context:
            content = [text_context + "\n\n" + prompt]
        else:
            content = [prompt, *(images or [])]
        ...

    def generate_text(
        self,
        prompt: str,
        images: list[Image.Image] | None = None,
        retries: int = settings.extraction_retries,
        text_context: str | None = None,          # ← NEW
    ) -> str:
        ...
        # Build content array
        if text_context:
            content = [text_context + "\n\n" + prompt]
        else:
            content = [prompt, *(images or [])]
        ...
```

**Key design decision:** When `text_context` is provided, images are not sent at all — Gemini receives a single text blob (structured document text + prompt). This eliminates the multi-MB image payload.

---

### 4. Modified File: `src/services/extraction_service.py`

#### 4a. ExtractionService dataclass — new optional field

```python
@dataclass
class ExtractionService:
    renderer: PdfRenderer
    llm_client: GeminiExtractionClient
    mistral_ocr: MistralOcrClient | None = None   # ← NEW (None = feature off)
```

#### 4b. extract_file_records — new orchestration logic

```python
def extract_file_records(self, pdf_path, source_file, attributes):
    # ── Step 0: Attempt Mistral OCR (once for entire request) ──────────
    structured_text: str | None = None
    if self.mistral_ocr is not None:
        try:
            structured_text = self.mistral_ocr.extract_text(pdf_path)
            if len(structured_text) < 50:
                logger.warning("Mistral OCR returned only %d chars, falling back to images", len(structured_text))
                structured_text = None
        except Exception as exc:
            logger.warning("Mistral OCR failed (%s: %s), falling back to images", type(exc).__name__, exc)
            structured_text = None

    # ── Phase 1: Classification ─────────────────────────────────────────
    if structured_text:
        # Text-based classification (fast — no image upload)
        doc_type = self.llm_client.generate_text(
            CLASSIFICATION_PROMPT_TEXT,
            text_context=structured_text,
        )
    else:
        # Image-based classification (fallback)
        images = self.renderer.render_to_images(pdf_path)
        doc_type = self.llm_client.generate_text(
            CLASSIFICATION_PROMPT_IMAGE, images=images
        )

    # ... validation check (unchanged) ...

    # ── Phase 2: Extraction ─────────────────────────────────────────────
    ocr_index = self._get_or_build_ocr_index(pdf_path)  # Always for bbox

    if structured_text:
        # Text-based extraction (fast)
        prompt = build_dynamic_prompt_text(attributes)
        schema = build_response_schema(attributes)
        data = self.llm_client.generate_json(
            prompt, text_context=structured_text, response_schema=schema
        )
    else:
        # Image-based extraction (fallback)
        if not images:
            images = self.renderer.render_to_images(pdf_path)
        prompt = build_dynamic_prompt(attributes)
        schema = build_response_schema(attributes)
        data = self.llm_client.generate_json(prompt, images=images, response_schema=schema)

    document_type, records = _coerce_records(data, attributes, ocr_index)
    # ... rest unchanged ...
```

#### 4c. New prompt variants

```python
CLASSIFICATION_PROMPT_TEXT = """
You are analyzing structured OCR text extracted from a government document.
Your ONLY task is to classify the document type.

The full document text is provided above. Classify it as EXACTLY ONE of:
- "letter of award (loa)"
- "completion certificate (cc)"
- "provisional completion certificate (pcc)"
- "financial closure"
- "other"

Return ONLY the classification string, nothing else.
"""

def build_dynamic_prompt_text(attributes: list[str]) -> str:
    """Same as build_dynamic_prompt but adapted for structured OCR text input."""
    fields = "\n".join(f"- {attr}" for attr in attributes)
    return f"""
You are a precise data extractor for official government documents.
The structured OCR text of the document is provided above.
...
(same grounding rules, but references "the text above" instead of "images")
...
Extract the following fields:
{fields}
...
"""
```

#### 4d. build_extraction_service factory

```python
def build_extraction_service() -> ExtractionService:
    from src.services.settings import settings

    renderer = PdfRenderer()
    llm_client = GeminiExtractionClient()

    mistral_ocr: MistralOcrClient | None = None
    if settings.use_mistral_ocr:
        if not settings.mistral_api_key:
            raise ValueError("MISTRAL_API_KEY must be set when USE_MISTRAL_OCR is enabled")
        from src.services.mistral_ocr_client import MistralOcrClient
        mistral_ocr = MistralOcrClient(
            api_key=settings.mistral_api_key,
            model=settings.mistral_ocr_model,
        )

    return ExtractionService(
        renderer=renderer,
        llm_client=llm_client,
        mistral_ocr=mistral_ocr,
    )
```

---

### 5. Modified File: `requirements.txt`

```
pydantic>=2.0
pandas
python-dotenv
fastapi
uvicorn[standard]
python-multipart
jinja2
google-generativeai
PyMuPDF
Pillow
openpyxl
pytesseract
rapidfuzz
mistralai>=1.0.0
```

---

## Data Models

### Structured_Text

A plain Python `str` containing the markdown representation of the full PDF content. Pages are separated by `"\n\n"`. This is the only new data type introduced — it flows through the system as a local variable, not a persisted entity.

### ExtractionService (modified)

```python
@dataclass
class ExtractionService:
    renderer: PdfRenderer
    llm_client: GeminiExtractionClient
    mistral_ocr: MistralOcrClient | None = None   # NEW — None means feature off
```

### AppSettings (modified)

```python
@dataclass(frozen=True)
class AppSettings:
    # ... existing fields unchanged ...
    mistral_api_key: str | None = None             # NEW
    mistral_ocr_model: str = "mistral-ocr-latest"  # NEW
    use_mistral_ocr: bool = False                   # NEW (True when key is set)
```

### All existing models unchanged

- `SourceMeta` — no changes
- `OcrIndexEntry` / `OcrIndex` — no changes
- `ExtractionResponse` (Pydantic schema for Gemini) — no changes
- JSON/CSV response shapes — no changes

---

## Sequence Diagram

```
User          app.py           ExtractionService     MistralOcrClient    GeminiClient     PdfRenderer
 │               │                    │                    │                  │                │
 │──POST /extract──▶│                    │                    │                  │                │
 │               │──extract_file_records──▶│                    │                  │                │
 │               │                    │                    │                  │                │
 │               │                    │──extract_text(pdf)──▶│                  │                │
 │               │                    │                    │──Mistral API──▶   │                │
 │               │                    │                    │◀──markdown text──  │                │
 │               │                    │◀──structured_text───│                  │                │
 │               │                    │                    │                  │                │
 │               │                    │──generate_text(classify_prompt, text_context)──▶│        │
 │               │                    │◀──"letter of award (loa)"──────────────────────│        │
 │               │                    │                    │                  │                │
 │               │                    │   [validation passes]                 │                │
 │               │                    │                    │                  │                │
 │               │                    │──────────────────────────────────────────────────────▶│
 │               │                    │                    │                  │   extract_words (Tesseract)
 │               │                    │◀─────────────────────────────────────────────ocr_index──│
 │               │                    │                    │                  │                │
 │               │                    │──generate_json(extract_prompt, text_context)───▶│       │
 │               │                    │◀──{records: [...]}─────────────────────────────│       │
 │               │                    │                    │                  │                │
 │               │                    │  [_coerce_source_meta with ocr_index]          │       │
 │               │                    │                    │                  │                │
 │               │◀──{records, document_validity}──│                    │                  │   │
 │◀──JSON response──│                    │                    │                  │                │
```

---

## Data Flow

```
                         ┌────────────────────────┐
                         │     PDF File (input)   │
                         └────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                    │
              ▼                   ▼                    ▼
┌─────────────────────┐  ┌──────────────┐  ┌──────────────────┐
│  MistralOcrClient   │  │ PdfRenderer  │  │  PdfRenderer     │
│  .extract_text()    │  │ .render_to_  │  │  .extract_words_ │
│  → structured_text  │  │  images()    │  │   from_pdf()     │
│  (for Gemini)       │  │ (fallback    │  │  (for bbox/      │
│                     │  │  only)       │  │   source_meta)   │
└──────────┬──────────┘  └──────┬───────┘  └────────┬─────────┘
           │                    │                    │
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────────────────────────┐  ┌──────────────────┐
│  GeminiExtractionClient              │  │   OCR_Index      │
│  .generate_text(text_context=...)    │  │   (word-level    │
│  .generate_json(text_context=...)    │  │    bboxes)       │
│  OR                                  │  │                  │
│  .generate_text(images=[...])        │  │                  │
│  .generate_json(images=[...])        │  │                  │
└──────────────────┬───────────────────┘  └────────┬─────────┘
                   │                                │
                   ▼                                ▼
         ┌─────────────────────────────────────────────────┐
         │  _coerce_records() + _coerce_source_meta()      │
         │  → final records with values + bbox coordinates │
         └─────────────────────────────────────────────────┘
```

---

## Performance Budget

| Step | Current (Image Path) | New (Mistral Path) |
|------|---------------------|-------------------|
| Render pages to JPEG | ~2–3s | **Skipped** (for Gemini) |
| Upload images to Gemini (Phase 1) | ~3–5s | **Skipped** |
| Upload images to Gemini (Phase 2) | ~5–8s | **Skipped** |
| Mistral OCR call | N/A | ~2–5s |
| Gemini classify (text only) | N/A | ~1–2s |
| Gemini extract (text only) | N/A | ~2–4s |
| Tesseract OCR (for bbox) | ~2–4s | ~2–4s (unchanged) |
| **Total** | **15–20s** | **≤10s** |

---

## Error Handling

| Scenario | Action |
|----------|--------|
| `mistralai` not installed | `ImportError` with install message |
| Mistral API timeout (>8s) | `TimeoutError` → fallback to images |
| Mistral auth failure | Exception → fallback to images |
| Mistral returns <50 chars | Warning logged → fallback to images |
| Gemini failure (text path) | Same retry logic as current (2 retries) |
| Tesseract not installed | OCR index empty, bbox = None (unchanged) |
| `use_mistral_ocr=True` but no key | `ValueError` raised at startup |

## Correctness Properties

### Property 1: Exactly-once Mistral call
`extract_text()` is called once per document, result stored in local variable and reused for Phase 1 + Phase 2. No second API call occurs within the same `extract_file_records` invocation.

- **Validates: Requirement 1.4, Requirement 4.3**

### Property 2: Fallback isolation
The image-based path is triggered only when `structured_text is None`. No hybrid mixing of text + images occurs within a single Gemini call.

- **Validates: Requirement 1.5, Requirement 1.6**

### Property 3: Bbox independence
Tesseract OCR always runs (via `_get_or_build_ocr_index`) for `source_meta` regardless of which LLM input path is used. Bounding boxes are never affected by the Mistral integration.

- **Validates: Requirement 3.2, Requirement 3.4**

### Property 4: Response shape invariance
Output JSON/CSV structure is identical for both text and image paths. No new keys are added to the response; no existing keys are removed.

- **Validates: Requirement 7.1, Requirement 7.3**

### Property 5: Feature toggle
Setting `USE_MISTRAL_OCR=false` (or removing `MISTRAL_API_KEY`) produces byte-identical behaviour to pre-change code. The `mistral_ocr` field is `None` and all branching skips the Mistral path.

- **Validates: Requirement 5.3**

---

## Files Changed Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `src/services/mistral_ocr_client.py` | **NEW** | MistralOcrClient class |
| `src/services/settings.py` | MODIFIED | Add 3 new fields |
| `src/services/llm_client.py` | MODIFIED | Add `text_context` parameter |
| `src/services/extraction_service.py` | MODIFIED | New orchestration, new prompts, factory update |
| `requirements.txt` | MODIFIED | Add `mistralai>=1.0.0` |
| `.env` | MODIFIED (user) | Add `MISTRAL_API_KEY=...` |

---

## Testing Strategy

1. **Unit test MistralOcrClient** — mock Mistral SDK, verify extract_text returns joined markdown
2. **Unit test LLM_Client** — verify text_context path sends text-only content, no images
3. **Integration test** — upload a real PDF, verify full pipeline returns correct extraction in <10s
4. **Fallback test** — set invalid MISTRAL_API_KEY, verify system falls back to image path gracefully
5. **Feature-off test** — unset MISTRAL_API_KEY, verify system works exactly as before

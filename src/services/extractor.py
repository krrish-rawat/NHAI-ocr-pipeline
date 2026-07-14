"""Phase 2 per-field extractor using mistral-large-latest.

Each field is extracted in a separate LLM call. Results are cached by
(sha256(ocr_text), normalize(field_name)) to guarantee output stability:
adding a new field to a request never changes the value of existing fields.
"""
import json
import logging
from typing import Any

from pydantic import ValidationError
from src.services.models import FieldExtraction
from src.services.utils import cache_key, normalize_text

logger = logging.getLogger(__name__)


# ── Extraction prompt ─────────────────────────────────────────────────────────

SINGLE_FIELD_SYSTEM_PROMPT = """\
You are a precise field extractor for official NHAI (National Highways Authority of India) government documents.
You will be given structured OCR text from a document and a single field name to extract.

HARD RULE — anti-hallucination (NEVER violate this):
  The value you return MUST appear verbatim (word-for-word) in the OCR text provided above.
  If the exact value is not present in the text, return value: "Null".
  Do NOT infer, estimate, calculate, or supply values from outside knowledge.

SOFT RULE — semantic identification:
  You do NOT need an explicit label printed immediately adjacent to the value.
  Read the meaning of the surrounding sentence or clause to determine whether it
  refers to the requested field.

  For example, the sentence:
    "The total contract value for the above work is Rs. 487.32 Crore."
  supports a field named "Contract Value" even though the words "Contract Value"
  do not appear directly next to "Rs. 487.32 Crore".

CONTEXT DISCIPLINE:
  If the only candidate value appears in a clause whose context clearly describes
  a DIFFERENT field (e.g. "Rs. 100 Crore" appears in a penalty clause, not a
  contract award clause), return value: "Null" — do not borrow that value.

DATE RULE:
  Preserve date formats exactly as written in the OCR text. Do not reformat,
  reorder, or convert dates. Return compound date values (multiple dates joined
  in one clause, e.g. "13.03.2025 & 02.07.2025") as the full joined string.

OUTPUT (JSON only — no markdown, no explanation):
  {"value": "<verbatim value from text, or Null>",
   "source_text": "<shortest sentence or phrase from text that states the value
                   and supports this field by meaning, or Null>"}
"""


# JSON schema for structured output (used with Mistral's json_schema response format)
FIELD_EXTRACTION_SCHEMA: dict[str, Any] = {
    "name": "field_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "source_text": {"type": "string"},
        },
        "required": ["value", "source_text"],
        "additionalProperties": False,
    },
}


def _build_single_field_prompt(field_name: str, ocr_text: str) -> str:
    """Build the user-turn prompt for extracting a single field from OCR text."""
    return (
        f"OCR TEXT:\n{ocr_text}\n\n"
        f"FIELD TO EXTRACT: {field_name}\n\n"
        "Return JSON only."
    )


class MistralExtractor:
    """Phase 2 per-field extractor using mistral-large-latest.

    Each field is extracted in a separate LLM call. Results are cached by
    cache_key(ocr_text, field_name) = (sha256(ocr_text), normalize(field_name)).

    Output stability guarantee: once a (ocr_text, field_name) pair is extracted,
    the result is returned from cache on every subsequent call — adding more fields
    to the same request NEVER changes previously extracted values.

    The cache is per-extractor-instance and is cleared between requests so that
    PII from one document is never retained when a new document is processed.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-large-latest",
        retries: int = 1,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.retries = retries
        self._cache: dict[tuple[str, str], FieldExtraction] = {}
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from mistralai.client.sdk import Mistral
            except ImportError:
                from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key)
        return self._client

    def _call_llm(self, field_name: str, ocr_text: str) -> FieldExtraction:
        """Make the LLM call with retry and Pydantic validation."""
        client = self._get_client()
        user_content = _build_single_field_prompt(field_name, ocr_text)

        for attempt in range(self.retries + 1):
            try:
                response = client.chat.complete(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SINGLE_FIELD_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    response_format={
                        "type": "json_object",
                    },
                    temperature=0.0,
                )
                raw_text = response.choices[0].message.content or "{}"
                # Strip markdown code fences if the model added them
                if raw_text.startswith("```"):
                    lines = [l for l in raw_text.split("\n") if not l.strip().startswith("```")]
                    raw_text = "\n".join(lines)
                parsed = json.loads(raw_text)
                result = FieldExtraction.model_validate(parsed)
                return result
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning(
                    "Extraction validation failed (attempt %d/%d) for field %r: %s",
                    attempt + 1, self.retries + 1, field_name, exc,
                )
                if attempt >= self.retries:
                    return FieldExtraction(value="Null", source_text="Null")
            except Exception as exc:
                logger.warning(
                    "Extraction LLM call failed (attempt %d/%d) for field %r: %s",
                    attempt + 1, self.retries + 1, field_name, exc,
                )
                if attempt >= self.retries:
                    return FieldExtraction(value="Null", source_text="Null")

        return FieldExtraction(value="Null", source_text="Null")

    def _apply_grounding_check(self, result: FieldExtraction, ocr_text: str) -> FieldExtraction:
        """Enforce the HARD grounding rule: value must appear verbatim in OCR text.

        If the value is non-Null but cannot be found (even after normalization)
        in the OCR text, overwrite with Null to prevent hallucination leakage.
        """
        if result.value == "Null":
            return result
        if normalize_text(result.value) in normalize_text(ocr_text):
            return result
        logger.debug(
            "Grounding check failed: value %r not found in OCR text — overwriting with Null",
            result.value,
        )
        return FieldExtraction(value="Null", source_text="Null")

    def extract_field(self, ocr_text: str, field_name: str) -> FieldExtraction:
        """Extract a single field from OCR text with stability-cache lookup.

        Cache hit: returns stored FieldExtraction without calling the model.
        Cache miss: calls the model, validates, applies grounding check, stores.
        """
        key = cache_key(ocr_text, field_name)

        if key in self._cache:
            logger.debug("Cache hit for field %r", field_name)
            return self._cache[key]

        logger.debug("Cache miss for field %r — calling LLM", field_name)
        result = self._call_llm(field_name, ocr_text)
        result = self._apply_grounding_check(result, ocr_text)
        self._cache[key] = result
        return result

    def extract_fields(
        self, ocr_text: str, field_names: list[str]
    ) -> dict[str, FieldExtraction]:
        """Extract multiple fields, reusing cache results where available.

        Returns a dict mapping each field_name to its FieldExtraction.
        Normalized field names are used as dict keys to match the cache keys.
        """
        results: dict[str, FieldExtraction] = {}
        for field_name in field_names:
            results[field_name] = self.extract_field(ocr_text, field_name)
        return results

    def clear_cache(self) -> None:
        """Clear the stability cache. Called between requests to prevent PII retention."""
        self._cache.clear()

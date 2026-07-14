# Design Document: NHAI PDF Data Extraction Rebuild

## Overview

This document describes the technical design for the production-quality rebuild of the NHAI PDF Data Extraction tool. The tool lets a single operator upload NHAI official PDFs, specify which fields to extract, and receive stable structured output (JSON/CSV) with each value grounded in verbatim source text.

The rebuild follows the same two-phase pipeline proven in the prototype — PDF upload → OCR → Phase 1 classify/gate → Phase 2 per-field extraction → serialized output — while making three targeted fixes:

1. **Output stability** (R5, critical): per-field extraction with an in-process stability cache so adding a field never perturbs results for existing fields.
2. **Semantic grounding** (R4 LOA/prose bug): a rewritten single-field prompt that enforces verbatim presence as a hard rule while relaxing the "explicit adjacent label" requirement to a soft semantic rule.
3. **Pydantic validation on LLM output** (missing from prototype): structured response validation with automatic retry on schema violation.

The runtime stack is fixed: Python 3.12+, FastAPI, Pydantic v2, Jinja2, vanilla JS ES modules, Mistral OCR + Mistral chat models (one API key for all three calls). No Gemini dependency.

Requirement 11 (Document-Type Field Schemas) is **deferred** and intentionally omitted from this design.

---

## Architecture

### High-Level Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        Browser / Web_UI                       │
│  static/                                                       │
│    api.js  ui.js  lang.js  progress.js  validation.js         │
│    (ES modules, no build step)                                 │
└─────────────────────┬────────────────────────────────────────┘
                      │ HTTP JSON (POST /extract, POST /classify)
                      ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (app.py)                  │
│                                                               │
│  api/routes.py                                                │
│    POST /extract    POST /classify    GET /health             │
│    GET /  (Jinja2 HTML template)                              │
│                                                               │
│  services/                                                    │
│  ┌──────────────┐  ┌─────────────┐  ┌───────────────────┐   │
│  │ ocr_service  │  │ classifier  │  │    extractor      │   │
│  │ (single OCR  │  │ (small model│  │  (large model,    │   │
│  │  base64 call)│  │ text prompt)│  │  per-field calls, │   │
│  └──────┬───────┘  └──────┬──────┘  │  stability cache) │   │
│         │                 │         └─────────┬─────────┘   │
│         └─────────────────┴──────────────────┘              │
│                           │                                   │
│                    pipeline.py                                │
│              (OCR → classify → extract → serialize)           │
│                                                               │
│  services/models.py     (Pydantic data models)                │
│  services/serializers.py (JSON / CSV output)                  │
│  services/settings.py   (Pydantic BaseSettings, env vars)     │
└─────────────────────────────────────────────────────────────┘
                      │
                      │ HTTPS API calls (single MISTRAL_API_KEY)
                      ▼
         ┌─────────────────────────────┐
         │     Mistral API Platform    │
         │                             │
         │  mistral-ocr-latest  (OCR)  │
         │  mistral-small-latest (cls) │
         │  mistral-large-latest (ext) │
         └─────────────────────────────┘
```

### Sequence Diagrams

#### Happy Path (accepted document, text-first OCR)

```
Operator        Browser          FastAPI           Mistral API
   │   upload+fields │                │                   │
   │────────────────>│  POST /extract │                   │
   │                 │───────────────>│                   │
   │                 │                │── OCR(base64) ───>│
   │                 │                │<── markdown text ─│
   │                 │                │                   │
   │                 │                │── classify(text) >│
   │                 │                │<── doc_type ──────│
   │                 │                │                   │
   │                 │          [accepted type]            │
   │                 │                │                   │
   │                 │                │  for each field:  │
   │                 │                │  [cache miss?]    │
   │                 │                │──extract(field)──>│
   │                 │                │<─{value,src_text}─│
   │                 │                │  [store in cache] │
   │                 │                │                   │
   │                 │  JSON response │                   │
   │<────────────────│<───────────────│                   │
```

#### Fallback Path (OCR text too short or OCR call fails)

```
Operator        Browser          FastAPI           Mistral API
   │   upload+fields │                │                   │
   │────────────────>│  POST /extract │                   │
   │                 │───────────────>│                   │
   │                 │                │── OCR(base64) ───>│
   │                 │                │<── short text / error
   │                 │                │                   │
   │                 │          [fallback triggered]       │
   │                 │                │                   │
   │                 │                │── classify(images)>│
   │                 │                │<── doc_type ───────│
   │                 │                │                   │
   │                 │                │── extract(images) >│  (per-field)
   │                 │                │<─ {value,src_text}─│
   │                 │                │                   │
   │                 │  JSON response │                   │
   │<────────────────│<───────────────│                   │
```

#### Other Document + Force Extract

```
Operator        Browser          FastAPI
   │   upload+fields │                │
   │────────────────>│  POST /extract │
   │                 │───────────────>│
   │                 │                │ [classify → "other"]
   │                 │ {rejected, doc_type:"other"}
   │<────────────────│<───────────────│
   │                 │                │
   │  Force Extract  │                │
   │────────────────>│ POST /extract  │
   │                 │ force_extract=true
   │                 │───────────────>│
   │                 │                │ [bypass gate, run extraction]
   │                 │  JSON response │
   │<────────────────│<───────────────│
```

---

## Components and Interfaces

### `services/ocr_service.py` — MistralOcrClient

Converts an uploaded PDF to structured markdown text via a single Mistral OCR call. The PDF is read from disk and encoded as a base64 data URI — no separate file upload or signed-URL step.

```python
class MistralOcrClient:
    def extract_text(self, pdf_path: str) -> str:
        """
        Returns: concatenated markdown text for all pages.
        Raises:  OcrError on API failure (caught by pipeline for fallback).
        """
```

The client is instantiated once per application startup and reuses the underlying HTTP connection. Timeout: configurable (default 60 s).

### `services/classifier.py` — MistralClassifier

Phase 1 classification using `mistral-small-latest`. Accepts OCR text (text path) or page images (fallback path). Returns exactly one type string.

```python
class MistralClassifier:
    def classify(self, ocr_text: str) -> str:
        """
        Returns one of: "letter of award (loa)", "completion certificate (cc)",
        "provisional completion certificate (pcc)", "financial closure",
        "debarment records", "other"
        Temperature: 0.  Model: mistral-small-latest.
        """

    def classify_from_images(self, image_paths: list[str]) -> str:
        """Fallback: classify from rendered page images."""
```

### `services/extractor.py` — MistralExtractor

Phase 2 per-field extraction using `mistral-large-latest`. Each field is extracted in a separate LLM call. Results are cached by `(sha256(ocr_text), normalize(field_name))` for the duration of the request.

```python
class MistralExtractor:
    def extract_field(
        self,
        ocr_text: str,
        field_name: str,
    ) -> FieldExtraction:
        """
        Returns FieldExtraction(value, source_text).
        Cache hit: returns stored result without LLM call.
        Cache miss: calls LLM, validates with Pydantic, stores result.
        Temperature: 0.  Model: mistral-large-latest.
        """

    def extract_fields(
        self,
        ocr_text: str,
        field_names: list[str],
    ) -> dict[str, FieldExtraction]:
        """
        Calls extract_field for each field_name.
        Returns {field_name: FieldExtraction} for all requested fields.
        """

### `services/pipeline.py` — ExtractionPipeline

Orchestrates the full pipeline: validate → OCR → classify → gate → extract → build records. This is the single point of entry for all backend logic; route handlers call only this.

```python
class ExtractionPipeline:
    def run(
        self,
        pdf_path: str,
        source_file: str,
        field_names: list[str],
        force_extract: bool = False,
    ) -> ExtractionResponse:
        """
        Returns ExtractionResponse with doc_type, records, and status.
        Handles OCR fallback internally.
        Never raises — failures are captured in Output_Record.failure_reason.
        """
```

### `services/serializers.py` — Serializers

Pure functions, no side effects. Same interface as prototype but input types are now Pydantic models.

```python
def records_to_json(
    records: list[ExtractionRecord],
    field_names: list[str],
) -> str: ...

def records_to_csv(
    records: list[ExtractionRecord],
    field_names: list[str],
) -> str: ...
```

### `api/routes.py` — FastAPI Router

No business logic. Marshals HTTP into pipeline calls and pipeline results into HTTP responses.

```
POST /extract
  Body (multipart): file: UploadFile, fields: str, output_format: str, force_extract: bool
  Response 200: ExtractionResponse JSON  |  text/csv
  Response 400: validation error
  Response 413: file too large

POST /classify
  Body (multipart): file: UploadFile
  Response 200: {"doc_type": str}

GET /health
  Response 200: {"status": "ok", "mistral_key_present": bool}

GET /
  Response 200: HTML (Jinja2 index.html)
```

---

## Data Models

All models use Pydantic v2. Defined in `services/models.py`.

```python
from pydantic import BaseModel, field_validator
from typing import Literal

# ── Extraction output from LLM (single field) ───────────────────────────────

class FieldExtraction(BaseModel):
    """Shape the LLM must return for every single-field extraction call."""
    value: str
    source_text: str

    @field_validator("value", "source_text", mode="before")
    @classmethod
    def coerce_null(cls, v):
        if v is None or str(v).strip() == "":
            return "Null"
        return str(v).strip()


# ── Grounding confidence ─────────────────────────────────────────────────────

GroundingConfidence = Literal["high", "medium", "low", "unknown"]


# ── Source metadata attached to each field in an Output_Record ──────────────

class SourceMeta(BaseModel):
    text: str = "Null"
    confidence: GroundingConfidence = "unknown"


# ── One field's result inside an Output_Record ──────────────────────────────

class FieldResult(BaseModel):
    value: str = "Null"
    source_meta: SourceMeta = SourceMeta()


# ── One row of output (one document, potentially one table row) ──────────────

class ExtractionRecord(BaseModel):
    source_file: str
    fields: dict[str, FieldResult]  # key = normalized field name
    status: Literal["success", "failed", "rejected"] = "success"
    failure_reason: str = ""


# ── Full API response ────────────────────────────────────────────────────────

class ExtractionResponse(BaseModel):
    doc_type: str
    field_names: list[str]  # ordered, as requested
    records: list[ExtractionRecord]


# ── Settings (Pydantic BaseSettings) ────────────────────────────────────────

from pydantic_settings import BaseSettings

class AppSettings(BaseSettings):
    mistral_api_key: str
    mistral_ocr_model: str = "mistral-ocr-latest"
    mistral_classification_model: str = "mistral-small-latest"
    mistral_extraction_model: str = "mistral-large-latest"
    max_upload_bytes: int = 25 * 1024 * 1024   # 25 MB
    min_ocr_text_length: int = 100
    extraction_retries: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("mistral_api_key", mode="before")
    @classmethod
    def key_must_be_present(cls, v):
        if not v:
            raise ValueError(
                "MISTRAL_API_KEY is required. Set it as an environment variable."
            )
        return v
```

---

## Stability Cache Design

### Problem

The prototype extracted all requested fields in a single LLM call. Adding one field changed the prompt, which perturbed the model's other answers — even at temperature 0, the attention distribution shifts slightly. This is the root cause of R5.

### Solution: Per-Field Calls + In-Process Cache

Extract each field in its own LLM call. Cache the result by `(sha256(ocr_text), normalize(field_name))`. On cache hit, return the stored result without calling the model. This makes output stability a **structural property** of the cache, not a probabilistic promise about LLM determinism.

Temperature = 0 is still applied as defence-in-depth.

### Cache Scope

In-process, per-request lifetime. Implemented as a plain `dict` on the `MistralExtractor` instance. A new extractor instance (or a cleared cache) is used per pipeline run. There is no persistence across requests — this is intentional:

- Documents contain real PII and must not be retained after the request completes.
- In-memory caching within a single request is sufficient to achieve stability: the operator re-runs extraction by submitting a new request, and the cache ensures the *second* submission produces the same per-field results as the first (assuming same OCR text).

### Cache Key Definition

```python
import hashlib
import re

def _ocr_hash(ocr_text: str) -> str:
    return hashlib.sha256(ocr_text.encode("utf-8")).hexdigest()

def _normalize_field_name(field_name: str) -> str:
    return re.sub(r"\s+", " ", field_name.strip()).lower()

def _cache_key(ocr_text: str, field_name: str) -> tuple[str, str]:
    return (_ocr_hash(ocr_text), _normalize_field_name(field_name))
```

### Pseudocode

```python
class MistralExtractor:
    def __init__(self, client, model, retries):
        self._client = client
        self._model = model
        self._retries = retries
        self._cache: dict[tuple[str, str], FieldExtraction] = {}

    def extract_field(self, ocr_text: str, field_name: str) -> FieldExtraction:
        key = _cache_key(ocr_text, field_name)

        # Cache hit: return immediately, no LLM call
        if key in self._cache:
            return self._cache[key]

        # Cache miss: call the model
        prompt = _build_single_field_prompt(field_name, ocr_text)
        raw_json = self._client.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": FIELD_EXTRACTION_SCHEMA},
            temperature=0,
        )

        # Validate with Pydantic; retry once on failure; fall back to Null
        try:
            result = FieldExtraction.model_validate_json(raw_json)
        except ValidationError:
            if self._retries > 0:
                # One retry with the same prompt
                raw_json = self._client.chat(...)
                try:
                    result = FieldExtraction.model_validate_json(raw_json)
                except ValidationError:
                    result = FieldExtraction(value="Null", source_text="Null")
            else:
                result = FieldExtraction(value="Null", source_text="Null")

        # Enforce verbatim grounding hard rule before caching
        if result.value != "Null":
            norm_value = _normalize(result.value)
            norm_text = _normalize(ocr_text)
            if norm_value not in norm_text:
                result = FieldExtraction(value="Null", source_text="Null")

        self._cache[key] = result
        return result

    def clear_cache(self) -> None:
        self._cache.clear()
```

---

## Single-Field Extraction Prompt Design

### The Old Problem

The prototype prompt said (in effect): "find the phrase that LABELS this field and states the value". This works for tabular documents (LOA fee schedules) but silently fails on prose documents (LOA narrative sections, financial closures) where a value like "Rs. 487.32 Crore" is embedded in a sentence without a preceding label of exactly "Contract Value".

### New Prompt Design

Two rules, explicitly differentiated in the prompt:

- **HARD rule** (anti-hallucination): the value must appear verbatim in the OCR text. If it does not, return Null.
- **SOFT rule** (semantic grounding): identify *which* value belongs to this field by reading the *meaning* of surrounding sentences — not by looking for an exact adjacent label.

```python
SINGLE_FIELD_SYSTEM_PROMPT = """\
You are a precise field extractor for official government documents.
You will be given structured OCR text from a document and a single field name.
Your task: find the value for that field.

HARD RULE — anti-hallucination (NEVER violate):
  The value you return MUST appear verbatim in the OCR text provided.
  If the exact value is not present in the text, return value: "Null".

SOFT RULE — semantic identification:
  You do NOT need an explicit label adjacent to the value.
  Read the meaning of the surrounding sentence or clause to determine
  whether it refers to the requested field. A sentence like
  "The total contract value for the above work is Rs. 487.32 Crore"
  supports a field named "Contract Value" even though "Contract Value"
  is not printed next to "Rs. 487.32 Crore".

CONTEXT DISCIPLINE:
  If the only candidate value appears in a clause that clearly describes
  a DIFFERENT field (e.g. the value "Rs. 100 Crore" appears in a sentence
  about a penalty, not a contract award), return Null.

OUTPUT (JSON only, no markdown):
  {"value": "<verbatim value from text, or Null>",
   "source_text": "<shortest sentence/phrase from text that states the value
                   and supports this field by meaning, or Null>"}
"""

def _build_single_field_prompt(field_name: str, ocr_text: str) -> str:
    return (
        f"OCR TEXT:\n{ocr_text}\n\n"
        f"FIELD TO EXTRACT: {field_name}\n\n"
        "Return JSON only."
    )
```

---

## Module File Structure

```
Nhai-pdf-parser/
├── app.py                          # FastAPI app: mounts static, includes router, startup validation
├── requirements.txt
├── .env                            # MISTRAL_API_KEY and optional overrides (not committed)
│
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # FastAPI router: /extract, /classify, /health, GET /
│   │
│   └── services/
│       ├── __init__.py
│       ├── models.py               # Pydantic models: FieldExtraction, ExtractionRecord,
│       │                           #   ExtractionResponse, SourceMeta, AppSettings
│       ├── settings.py             # AppSettings singleton (reads env vars, fails fast)
│       ├── ocr_service.py          # MistralOcrClient (base64 inline, single call)
│       ├── classifier.py           # MistralClassifier (small model, text + image paths)
│       ├── extractor.py            # MistralExtractor (large model, per-field, stability cache)
│       ├── pipeline.py             # ExtractionPipeline (orchestrates all phases)
│       └── serializers.py          # records_to_json(), records_to_csv() (pure functions)
│
├── static/
│   ├── National_Highways_Authority_of_India_logo.svg
│   ├── styles.css                  # NHAI color scheme: navy #003366, saffron #FF9933
│   └── js/
│       ├── api.js                  # fetch wrappers: postExtract(), postClassify()
│       ├── ui.js                   # DOM manipulation: showResults(), showBanner(), etc.
│       ├── lang.js                 # i18n: EN/HI string map, applyLanguage()
│       ├── progress.js             # Progress indicator: show/hide/update
│       └── validation.js           # Client-side validation: file type, field count
│
└── templates/
    └── index.html                  # Jinja2 template; loads static/js/* as ES modules
```

---

## API Endpoint Contract

### `POST /extract`

**Request** (multipart/form-data):

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | UploadFile | yes | PDF file (max `MAX_UPLOAD_BYTES`) |
| `fields` | string | yes | Comma or newline separated field names |
| `output_format` | string | no | `"json"` (default) or `"csv"` |
| `force_extract` | string | no | `"true"` to bypass classification gate |

**Response 200 JSON** (`output_format=json`):
```json
{
  "doc_type": "letter of award (loa)",
  "field_names": ["Name", "Agreement Date", "Contract Value"],
  "records": [
    {
      "source_file": "sample_loa.pdf",
      "fields": {
        "Name": {
          "value": "M/s ABC Infrastructure Ltd",
          "source_meta": {"text": "This agreement is with M/s ABC Infrastructure Ltd", "confidence": "high"}
        },
        "Agreement Date": {
          "value": "15.03.2024",
          "source_meta": {"text": "Agreement dated 15.03.2024", "confidence": "high"}
        },
        "Contract Value": {
          "value": "Null",
          "source_meta": {"text": "Null", "confidence": "unknown"}
        }
      },
      "status": "success",
      "failure_reason": ""
    }
  ]
}
```

**Response 200 CSV** (`output_format=csv`):
```
source_file,Name,Agreement Date,Contract Value,status,failure_reason
sample_loa.pdf,M/s ABC Infrastructure Ltd,15.03.2024,Null,success,
```

**Error responses:**
- `400` — invalid file type, zero fields, malformed request
- `413` — file exceeds `MAX_UPLOAD_BYTES`

**Rejection response** (classified as "other", `force_extract` not set):
```json
{
  "doc_type": "other",
  "field_names": ["Name"],
  "records": [{
    "source_file": "invoice.pdf",
    "fields": {"Name": {"value": "Null", "source_meta": {"text": "Null", "confidence": "unknown"}}},
    "status": "rejected",
    "failure_reason": "Document classified as 'other' (not a recognized NHAI document type)"
  }]
}
```

### `POST /classify`

**Request** (multipart/form-data): `file: UploadFile`

**Response 200:**
```json
{"doc_type": "completion certificate (cc)"}
```

### `GET /health`

**Response 200:**
```json
{"status": "ok", "mistral_key_present": true}
```

### `GET /`

Returns Jinja2-rendered `index.html`. No template variables required at render time — all data flows through API calls.

---

## Frontend Module Structure

The frontend is framework-free vanilla JS using native ES module imports. No bundler, no transpiler, no `node_modules`.

```html
<!-- templates/index.html (simplified) -->
<script type="module" src="/static/js/api.js"></script>
<script type="module" src="/static/js/lang.js"></script>
<script type="module" src="/static/js/validation.js"></script>
<script type="module" src="/static/js/progress.js"></script>
<script type="module" src="/static/js/ui.js"></script>
```

### Module Responsibilities

**`api.js`** — all fetch calls, nothing else:
```javascript
export async function postExtract(formData) { ... }   // POST /extract
export async function postClassify(formData) { ... }  // POST /classify
```

**`ui.js`** — all DOM manipulation, imports from api.js, progress.js, lang.js:
```javascript
export function showResultsCard(response) { ... }
export function showRejectionBanner(docType, onForceExtract) { ... }
export function hideResultsCard() { ... }
export function renderFieldTable(fieldNames, records) { ... }
export function showErrorMessage(msg) { ... }
```

**`lang.js`** — i18n string map and language toggle:
```javascript
const STRINGS = {
  en: { upload: "Upload PDF", extract: "Extract Fields", ... },
  hi: { upload: "PDF अपलोड करें", extract: "फ़ील्ड निकालें", ... }
};
export function applyLanguage(lang) { /* updates all data-i18n elements */ }
export function getCurrentLang() { ... }
```

**`progress.js`** — progress indicator lifecycle:
```javascript
export function showProgress(message) { ... }
export function hideProgress() { ... }
export function updateProgress(message) { ... }
```

**`validation.js`** — client-side checks before submit:
```javascript
export function validateFile(file) { /* returns null or error string */ }
export function validateFields(fieldsText) { /* returns null or error string */ }
```

### UI Layout (single-column government style)

```
┌─────────────────────────────────────────┐
│  [NHAI Logo]  National Highways         │
│               Authority of India        │
│                              [EN | हिं]  │
├─────────────────────────────────────────┤
│  PDF Upload                             │
│  [────────── Drop or browse ──────────] │
│                                         │
│  Fields to extract                      │
│  [Name, Agreement Date, ...           ] │
│  (hint: be specific — e.g. "Agreement  │
│   Date" not just "Date")               │
│                                         │
│  [  Extract Fields  ]                   │
├─────────────────────────────────────────┤
│  ⚠ [REJECTION BANNER — hidden by default]
│  Document type not recognized.          │
│  [Force Extract Anyway]                 │
├─────────────────────────────────────────┤
│  ● Processing... (hidden by default)    │
├─────────────────────────────────────────┤
│  Results (hidden until complete)        │
│  Document type: Letter of Award (LOA)  │
│  ┌──────────┬────────────┬──────────┐   │
│  │ Field    │ Value      │ Source   │   │
│  ├──────────┼────────────┼──────────┤   │
│  │ Name     │ M/s ABC... │ "This …" │   │
│  │ Date     │ 15.03.2024 │ "Agree…" │   │
│  └──────────┴────────────┴──────────┘   │
│  [Download JSON]  [Download CSV]        │
└─────────────────────────────────────────┘
```

Colors: navy `#003366` (header, buttons), saffron `#FF9933` (accent), white background, dark grey body text.

---

## Performance Analysis: Per-Field Calls vs Batch

### Concern

Switching from one batch LLM call to N per-field calls naively multiplies API round trips. For 7 fields, that is 7× the latency.

### Why Per-Field Stays Within 10 Seconds

The critical insight is that the bottleneck in the prototype was OCR, not the LLM extraction call.

| Step | Prototype | Rebuild |
|---|---|---|
| OCR (Mistral, base64 inline) | ~3–4 s | ~3–4 s (unchanged) |
| Classification (small model) | ~0.5 s | ~0.5 s |
| Extraction (7 fields, batch) | ~2–3 s | — |
| Extraction (7 fields, per-field sequential) | — | ~5.25 s (7 × ~0.75 s) |
| **Total (sequential)** | **~6–7 s** | **~9–10 s** |

The per-field calls for `mistral-large-latest` are fast (0.5–1 s each) because the prompt is small (one focused field, not a 12-field JSON schema). The requirement is ≤10 s for 5–7 fields under normal conditions, which this satisfies.

**Further optimisation if needed**: extract fields concurrently using `asyncio.gather`. With 7 concurrent field calls, total extraction time collapses to ~1 s (time of the slowest single call). This is available as a straightforward upgrade path but is not required by the correctness constraints.

```python
# Optional concurrent extraction (upgrade path)
async def extract_fields_concurrent(self, ocr_text, field_names):
    tasks = [self.extract_field_async(ocr_text, f) for f in field_names]
    results = await asyncio.gather(*tasks)
    return dict(zip(field_names, results))
```

The stability cache applies equally to concurrent calls: the first call to complete for a given `(ocr_hash, field_name)` key populates the cache, and any subsequent call for the same key in the same request returns the cached result.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

The following five properties are the core correctness guarantees of the rebuild. Each is directly testable using a property-based testing library (e.g., [Hypothesis](https://hypothesis.readthedocs.io/) for Python) with a minimum of 100 iterations per property.

---

### Property 1: Output Stability

*For any* document OCR text and any set of requested field names, extracting the same field from the same OCR text more than once — whether in the same request or by varying which *other* fields are requested alongside it — SHALL return a character-for-character identical `value` and `source_text` on every invocation.

Concretely: if `extract_field(ocr_text, "Name")` returns `FieldExtraction(value="M/s ABC", source_text="...")` on the first call, every subsequent call with the same arguments must return the identical result.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

---

### Property 2: Verbatim Grounding

*For any* `FieldExtraction` returned by the extractor where `value` is not `"Null"`, the normalized `value` SHALL appear as a contiguous substring of the normalized OCR text used to produce it, where normalization means collapsing whitespace and lowercasing.

This property is enforced structurally by the post-validation grounding check in `MistralExtractor.extract_field` — any value that fails this check is overwritten with `"Null"` before caching or returning. The property test verifies the enforcement is actually applied.

**Validates: Requirements 4.2, 4.6**

---

### Property 3: Output Schema Stability

*For any* list of field names and any list of extraction records, the JSON output produced by `records_to_json` SHALL contain the keys `"doc_type"`, `"field_names"`, and `"records"`; every record SHALL contain every requested field name as a key; and the CSV output produced by `records_to_csv` SHALL have column headers in exactly the order `[source_file, *field_names, status, failure_reason]` with no extra or missing columns.

Additionally, for any string value in a record containing Hindi (Devanagari) or other non-ASCII Unicode characters, serialization through `records_to_json` and `records_to_csv` SHALL not corrupt or alter those characters.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.6**

---

### Property 4: Classification Gate

*For any* document OCR text, if the classifier returns `"other"` and `force_extract` is `False`, the pipeline SHALL return an `ExtractionResponse` whose every record has `status = "rejected"` and a non-empty `failure_reason`, with no field containing a non-Null value.

Conversely, *for any* document OCR text where `force_extract` is `True`, the pipeline SHALL proceed to Phase 2 extraction regardless of the classifier's output, and SHALL NOT return a `"rejected"` status.

**Validates: Requirements 3.3, 3.4**

---

### Property 5: OCR Single-Call Invariant and Stability Cache Hit Rate

*For any* pipeline run processing a single document with N requested fields (N ≥ 1), the `MistralOcrClient.extract_text` method SHALL be called exactly once. Additionally, for any field that appears more than once in the same request (after normalization), the `MistralExtractor` SHALL call the LLM exactly once for that field name, returning the cached result for subsequent occurrences.

**Validates: Requirements 9.2, 9.3, 5.5**

---

## Error Handling

### Failure modes and responses

| Failure mode | Handling | Client sees |
|---|---|---|
| File not a PDF | Reject immediately in route handler (magic bytes check) | 400 + descriptive error |
| File too large | Reject during streaming save | 413 |
| Zero fields after normalization | Reject in route handler | 400 |
| Mistral API key absent at startup | `AppSettings` validator raises `ValueError` → FastAPI refuses to start | Server log; deploy-time failure |
| OCR call fails or returns short text | `pipeline.py` catches and routes to fallback path | Transparent to operator |
| Both OCR paths fail | `pipeline.py` builds failure `ExtractionRecord` | `status: failed`, `failure_reason` set |
| LLM call returns invalid JSON | Pydantic `ValidationError` → retry once → return `FieldExtraction(Null, Null)` | Field value = "Null" |
| LLM returns value not in OCR text | Grounding hard-rule check overwrites to `FieldExtraction(Null, Null)` | Field value = "Null" |
| Unexpected exception in pipeline | Caught at route handler boundary; logged server-side; sanitized message to client | `status: failed`, generic message |

### Error message discipline

Route handlers never leak exception type names, stack traces, or internal paths to the client. All exceptions are caught, logged with full detail server-side, and returned as a safe generic message. This is the same discipline used in the prototype (`_safe_error_message`), formalized here.

### Startup validation

`AppSettings` uses a Pydantic `field_validator` on `mistral_api_key`. If the key is absent at process start, the import of `settings` raises `ValueError` with the message:

```
MISTRAL_API_KEY is required. Set it as an environment variable.
```

This causes FastAPI to fail during startup — not silently at the first request.

---

## Testing Strategy

### Overview

Testing combines unit tests (specific examples, error conditions, integration-point mocking) with property-based tests (the five correctness properties above). Unit tests cover concrete behavior; property tests verify universal correctness.

The property-based testing library is **Hypothesis** (Python). Each property test runs a minimum of 100 iterations with Hypothesis's default shrinking.

### Property-Based Tests

Each property maps to a Hypothesis test decorated with a comment referencing the design property.

```python
# Feature: nhai-extraction-rebuild, Property 1: Output Stability
@given(
    ocr_text=st.text(min_size=50),
    field_name=st.text(min_size=1, max_size=50).filter(str.strip)
)
@settings(max_examples=100)
def test_output_stability(ocr_text, field_name):
    extractor = MistralExtractor(client=MockMistralClient(), ...)
    result_1 = extractor.extract_field(ocr_text, field_name)
    result_2 = extractor.extract_field(ocr_text, field_name)  # cache hit
    assert result_1 == result_2
    # Also verify: extracting with different co-fields doesn't change this result
    _ = extractor.extract_field(ocr_text, "unrelated_field_xyz")
    result_3 = extractor.extract_field(ocr_text, field_name)
    assert result_1 == result_3
```

```python
# Feature: nhai-extraction-rebuild, Property 2: Verbatim Grounding
@given(
    ocr_text=st.text(min_size=20, alphabet=st.characters(blacklist_categories=["Cs"])),
    field_name=st.text(min_size=1, max_size=50)
)
@settings(max_examples=100)
def test_verbatim_grounding(ocr_text, field_name):
    extractor = MistralExtractor(client=MockMistralClient(returns_arbitrary_values=True), ...)
    result = extractor.extract_field(ocr_text, field_name)
    if result.value != "Null":
        normalized_value = _normalize(result.value)
        normalized_ocr = _normalize(ocr_text)
        assert normalized_value in normalized_ocr
```

```python
# Feature: nhai-extraction-rebuild, Property 3: Output Schema Stability
@given(
    field_names=st.lists(st.text(min_size=1, max_size=30), min_size=1, max_size=10),
    records=st.lists(build_extraction_record_strategy(), min_size=1, max_size=5)
)
@settings(max_examples=100)
def test_output_schema_stability(field_names, records):
    json_str = records_to_json(records, field_names)
    payload = json.loads(json_str)
    assert "doc_type" in payload
    assert "field_names" in payload
    assert "records" in payload
    for rec in payload["records"]:
        for fn in field_names:
            assert fn in rec["fields"]
    # CSV schema
    csv_str = records_to_csv(records, field_names)
    reader = csv.DictReader(io.StringIO(csv_str))
    assert list(reader.fieldnames) == ["source_file", *field_names, "status", "failure_reason"]
```

```python
# Feature: nhai-extraction-rebuild, Property 4: Classification Gate
@given(
    ocr_text=st.text(min_size=10),
    force_extract=st.booleans()
)
@settings(max_examples=100)
def test_classification_gate(ocr_text, force_extract):
    pipeline = ExtractionPipeline(
        ocr=MockOcr(returns=ocr_text),
        classifier=MockClassifier(returns="other"),
        extractor=MockExtractor()
    )
    response = pipeline.run("fake.pdf", "fake.pdf", ["Name"], force_extract=force_extract)
    if not force_extract:
        for rec in response.records:
            assert rec.status == "rejected"
            assert rec.failure_reason != ""
    else:
        # Extraction must have run (not rejected)
        for rec in response.records:
            assert rec.status != "rejected"
```

```python
# Feature: nhai-extraction-rebuild, Property 5: OCR Single-Call + Cache Hit Rate
@given(
    ocr_text=st.text(min_size=50),
    field_names=st.lists(st.text(min_size=1), min_size=2, max_size=8, unique=True)
)
@settings(max_examples=100)
def test_ocr_single_call_and_cache(ocr_text, field_names):
    mock_ocr = MockOcr(returns=ocr_text)
    extractor = MistralExtractor(client=CountingMockClient(), ...)
    pipeline = ExtractionPipeline(ocr=mock_ocr, ...)
    pipeline.run("fake.pdf", "fake.pdf", field_names)
    assert mock_ocr.call_count == 1
    # Duplicate field names (after normalization) use cache
    duplicated = field_names + [field_names[0].upper()]
    pipeline2 = ExtractionPipeline(ocr=MockOcr(returns=ocr_text), ...)
    pipeline2.run("fake.pdf", "fake.pdf", duplicated)
    # LLM call count for the duplicated field should be 1, not 2
    assert pipeline2.extractor.llm_call_count_for(field_names[0]) == 1
```

### Unit Tests

- `test_normalize_fields`: field deduplication preserves first-occurrence order, case-insensitive, whitespace-trimmed.
- `test_grounding_check`: `_grounding_check(value, source_text)` returns correct confidence level for all four cases.
- `test_ocr_fallback_trigger`: when OCR text length < `MIN_OCR_TEXT_LENGTH`, pipeline calls fallback, not primary path again.
- `test_ocr_error_fallback`: when `MistralOcrClient.extract_text` raises any exception, fallback is triggered.
- `test_double_failure`: when both OCR paths fail, `ExtractionRecord.status = "failed"` and `failure_reason` is non-empty.
- `test_pydantic_validation_retry`: when `MistralExtractor` receives invalid JSON from LLM, it retries once; on second failure it returns `Null`.
- `test_temperature_zero`: every `client.chat.complete` call is made with `temperature=0.0`.
- `test_invalid_file_type`: non-PDF content is rejected with 400.
- `test_file_too_large`: content exceeding `MAX_UPLOAD_BYTES` is rejected with 413.
- `test_health_endpoint`: `GET /health` returns `{"status": "ok"}` with key present.
- `test_settings_missing_key`: `AppSettings` raises `ValueError` when `MISTRAL_API_KEY` is absent.
- `test_csv_unicode`: Hindi characters round-trip through `records_to_csv` without corruption.

### Integration / Fixture Tests

These use real fixture documents (committed as small anonymized PDFs with no real PII) to verify end-to-end accuracy:

- `test_loa_extraction_known_values`: upload an LOA fixture; assert known field values match expected strings.
- `test_financial_closure_prose_values`: upload a financial closure fixture; assert values embedded in prose sentences are correctly extracted (validates the semantic grounding fix for R4).
- `test_debarment_extraction`: upload a debarment fixture; assert name and PAN fields are found.
- `test_other_document_rejected`: upload a non-NHAI PDF; assert `status = "rejected"` without `force_extract`.

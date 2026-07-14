# Implementation Plan: NHAI PDF Data Extraction Rebuild

## Overview

Bottom-up implementation of the NHAI PDF Data Extraction tool rebuild. Tasks are ordered by dependency: foundational data models and settings first, then service components, then the orchestrating pipeline, then API routes, then the frontend, then tests. Requirement 11 (Document-Type Field Schemas) is **DEFERRED** and intentionally absent.

All code is Python 3.12+ / FastAPI / Pydantic v2 on the backend; vanilla ES-module JS on the frontend.

---

## Tasks

- [x] 1. Establish project file structure and `requirements.txt`
  - Create all `__init__.py` files for `src/api/`, `src/services/`, `tests/`, `tests/fixtures/`
  - Create `static/js/` directory
  - Write `requirements.txt` with pinned versions for: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `mistralai`, `python-multipart`, `jinja2`, `aiofiles`, `hypothesis`, `pytest`, `pytest-asyncio`, `httpx`
  - _Requirements: R10 (configuration), R9 (runtime stack)_

- [x] 2. Implement core Pydantic data models (`src/services/models.py`)
  - [x] 2.1 Implement `FieldExtraction`, `GroundingConfidence`, `SourceMeta`, `FieldResult`, `ExtractionRecord`, `ExtractionResponse`
    - `FieldExtraction.coerce_null` validator: coerce `None` or blank string to `"Null"`
    - `ExtractionRecord.fields` is `dict[str, FieldResult]` keyed by normalized field name
    - `ExtractionResponse` carries `doc_type: str`, `field_names: list[str]`, `records: list[ExtractionRecord]`
    - _Requirements: R4.1, R4.7, R7.1, R7.2, R7.3, R7.4_

  - [ ]* 2.2 Write unit tests for `FieldExtraction.coerce_null` validator
    - Test: `None` → `"Null"`, empty string → `"Null"`, whitespace-only → `"Null"`, valid string preserved
    - _Requirements: R4.2_

- [x] 3. Implement `AppSettings` and startup validation (`src/services/settings.py`)
  - [x] 3.1 Implement `AppSettings(BaseSettings)` with `mistral_api_key`, `mistral_ocr_model`, `mistral_classification_model`, `mistral_extraction_model`, `max_upload_bytes`, `min_ocr_text_length`, `extraction_retries`; all with documented defaults
    - `field_validator("mistral_api_key", mode="before")` raises `ValueError("MISTRAL_API_KEY is required. Set it as an environment variable.")` when key is absent or blank
    - `model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}`
    - Export a module-level `settings = AppSettings()` singleton
    - _Requirements: R10.1, R10.2, R10.3, R10.4_

  - [ ]* 3.2 Write unit test `test_settings_missing_key`
    - Assert `AppSettings` raises `ValueError` / `ValidationError` when `MISTRAL_API_KEY` is absent from environment
    - _Requirements: R10.4_

- [x] 4. Implement field-name normalization utilities (`src/services/utils.py`)
  - [x] 4.1 Implement `normalize_field_name(field_name: str) -> str` (strip + collapse whitespace + lowercase), `ocr_hash(ocr_text: str) -> str` (sha256 hex), `cache_key(ocr_text, field_name) -> tuple[str, str]`, `normalize_text(text: str) -> str` (collapse whitespace + lowercase), `deduplicate_fields(fields: list[str]) -> list[str]` (preserve first-occurrence order, case-insensitive, whitespace-trimmed)
    - _Requirements: R1.5, R5.5_

  - [ ]* 4.2 Write unit test `test_normalize_fields`
    - Deduplication preserves first-occurrence order; strips surrounding whitespace; case-insensitive; handles empty input
    - _Requirements: R1.5_

- [x] 5. Implement `MistralOcrClient` (`src/services/ocr_service.py`)
  - [x] 5.1 Implement `MistralOcrClient.extract_text(pdf_path: str) -> str`
    - Read PDF bytes from disk; encode as base64 data URI; issue a single `mistral-ocr-latest` call (inline base64, not a signed URL)
    - Concatenate all page markdown sections into one string
    - Raise `OcrError` on any API failure or HTTP error
    - _Requirements: R2.1, R2.2, R9.2_

  - [ ]* 5.2 Write unit tests `test_ocr_fallback_trigger` and `test_ocr_error_fallback`
    - `test_ocr_fallback_trigger`: mock OCR returns text shorter than `min_ocr_text_length`; assert pipeline calls image-fallback path, not primary path again
    - `test_ocr_error_fallback`: mock `extract_text` raises exception; assert fallback is triggered
    - _Requirements: R2.3, R2.4_

- [x] 6. Implement `MistralClassifier` (`src/services/classifier.py`)
  - [x] 6.1 Implement `MistralClassifier.classify(ocr_text: str) -> str` and `classify_from_images(image_paths: list[str]) -> str`
    - `classify`: sends OCR text to `mistral-small-latest` at temperature 0; returns one of the six type strings (lower-case)
    - `classify_from_images`: sends rendered page images (fallback path) to the same model
    - Normalise the model response to one of: `"letter of award (loa)"`, `"completion certificate (cc)"`, `"provisional completion certificate (pcc)"`, `"financial closure"`, `"debarment records"`, `"other"`
    - _Requirements: R3.1, R3.5_

- [x] 7. Implement single-field extraction prompt (`src/services/extractor.py` — prompt module section)
  - [x] 7.1 Define `SINGLE_FIELD_SYSTEM_PROMPT`, `_build_single_field_prompt(field_name, ocr_text) -> str`, and `FIELD_EXTRACTION_SCHEMA` (JSON schema dict for `{"value": str, "source_text": str}`)
    - HARD rule in prompt: value MUST appear verbatim; if not, return `"Null"`
    - SOFT rule in prompt: identify field semantically from surrounding sentence meaning, not from adjacent label
    - Context discipline in prompt: if candidate value's clause clearly describes a different field, return `"Null"`
    - _Requirements: R4.2, R4.3, R4.4, R4.5_

- [x] 8. Implement `MistralExtractor` with stability cache (`src/services/extractor.py`)
  - [x] 8.1 Implement `MistralExtractor.__init__`, `_cache: dict[tuple[str,str], FieldExtraction]`, `extract_field(ocr_text, field_name) -> FieldExtraction`, `extract_fields(ocr_text, field_names) -> dict[str, FieldExtraction]`, `clear_cache()`
    - Cache key: `(ocr_hash(ocr_text), normalize_field_name(field_name))`
    - Cache hit: return stored result immediately, no LLM call
    - Cache miss: call `mistral-large-latest` at temperature 0 with `response_format` JSON schema
    - Pydantic `FieldExtraction.model_validate_json(raw_json)` on response; on `ValidationError` retry once; on second failure return `FieldExtraction(value="Null", source_text="Null")`
    - Post-validation grounding hard-rule check: if `result.value != "Null"` and `normalize_text(result.value) not in normalize_text(ocr_text)`, overwrite with `FieldExtraction(value="Null", source_text="Null")`
    - Store result in `_cache` before returning
    - _Requirements: R4.1, R4.2, R4.6, R5.1, R5.2, R5.3, R5.4, R5.5, R5.6_

  - [ ]* 8.2 Write unit test `test_pydantic_validation_retry`
    - Mock LLM client returns invalid JSON first call, valid JSON second call; assert extractor returns valid result
    - Mock LLM client returns invalid JSON both calls; assert extractor returns `FieldExtraction(value="Null", source_text="Null")`
    - _Requirements: R4.2_

  - [ ]* 8.3 Write unit test `test_temperature_zero`
    - Assert every `client.chat.complete` (or equivalent) call made by extractor and classifier passes `temperature=0.0`
    - _Requirements: R5.6_

- [x] 9. Implement grounding confidence scorer (`src/services/utils.py` — add to existing file)
  - [x] 9.1 Implement `score_grounding(value: str, source_text: str) -> GroundingConfidence`
    - `"high"` when normalized value is a contiguous substring of normalized source_text
    - `"medium"` when every token of normalized value appears in normalized source_text but not contiguously
    - `"low"` when one or more tokens of a non-Null value are absent from source_text
    - `"unknown"` when value is `"Null"`
    - _Requirements: R4.7_

  - [ ]* 9.2 Write unit test `test_grounding_check`
    - Four concrete examples covering all four confidence levels
    - _Requirements: R4.7_

- [x] 10. Implement `Serializers` (`src/services/serializers.py`)
  - [x] 10.1 Implement `records_to_json(records: list[ExtractionRecord], field_names: list[str]) -> str` and `records_to_csv(records: list[ExtractionRecord], field_names: list[str]) -> str`
    - JSON: output `{"doc_type": ..., "field_names": [...], "records": [...]}` — field_names in requested order; each record contains every requested field (emit `"Null"` if absent); include `status` and `failure_reason`
    - CSV columns in order: `source_file`, one column per field in requested order, `status`, `failure_reason`; emit `"Null"` for absent fields
    - Both serializers preserve Unicode (Hindi / Devanagari) characters without corruption; use `ensure_ascii=False` in JSON
    - Pure functions: no side effects, no file I/O
    - _Requirements: R7.1, R7.2, R7.3, R7.4, R7.5, R7.6_

  - [ ]* 10.2 Write unit test `test_csv_unicode`
    - Construct a record with Hindi characters in a field value; round-trip through `records_to_csv`; assert characters are identical
    - _Requirements: R7.6_

- [x] 11. Implement `ExtractionPipeline` orchestrator (`src/services/pipeline.py`)
  - [x] 11.1 Implement `ExtractionPipeline.__init__` accepting `ocr`, `classifier`, `extractor`, `settings` dependencies
    - _Requirements: R1.1, R2.1, R3.1_

  - [x] 11.2 Implement `ExtractionPipeline.run(pdf_path, source_file, field_names, force_extract=False) -> ExtractionResponse`
    - Step 1 — OCR: call `ocr.extract_text(pdf_path)`; if result shorter than `min_ocr_text_length` or raises `OcrError`, call image-fallback path
    - Step 2 — Classify: call `classifier.classify(ocr_text)` (or `classify_from_images` on fallback)
    - Step 3 — Gate: if `doc_type == "other"` and not `force_extract`, return rejection `ExtractionRecord` with `status="rejected"` and descriptive `failure_reason`
    - Step 4 — Extract: call `extractor.extract_fields(ocr_text, field_names)`; compute grounding confidence per field via `score_grounding`; build `FieldResult` and `ExtractionRecord`
    - Step 5 — Return `ExtractionResponse(doc_type, field_names, records)`
    - Never raises — all exceptions caught and surfaced in `ExtractionRecord.failure_reason`
    - _Requirements: R1.1, R2.3, R2.4, R2.5, R3.2, R3.3, R3.4, R3.5, R4.1, R5.3, R9.3_

  - [ ]* 11.3 Write unit test `test_double_failure`
    - Both primary OCR and image-fallback raise exceptions; assert `ExtractionRecord.status == "failed"` and `failure_reason` is non-empty
    - _Requirements: R2.5_

- [x] 12. Checkpoint — core backend complete
  - Ensure all unit tests pass: `pytest tests/unit/ -v`
  - Fix any import errors or type errors before proceeding.

- [x] 13. Implement FastAPI app entry point and API routes (`app.py`, `src/api/routes.py`)
  - [x] 13.1 Implement `app.py`: create `FastAPI` app; import `settings` singleton at module level (triggers startup validation); mount `static/` directory; include `api_router`; add Jinja2 `TemplateResponse` for `GET /`
    - Import of `settings` at module level ensures fail-fast on missing key before any request
    - _Requirements: R8.1, R10.4, R10.5_

  - [x] 13.2 Implement `POST /extract` route
    - Accept `file: UploadFile`, `fields: str`, `output_format: str = "json"`, `force_extract: str = "false"`
    - Validate content type / magic bytes (first 5 bytes `%PDF-`); return 400 if not PDF
    - Check file size ≤ `max_upload_bytes`; return 413 if exceeded
    - Parse, deduplicate, and validate fields (at least 1 after normalization); return 400 if empty
    - Save PDF to temp file; call `ExtractionPipeline.run`; serialize and return result
    - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R3.2, R3.3, R3.4_

  - [x] 13.3 Implement `POST /classify` route
    - Accept `file: UploadFile`; save to temp file; call `classifier.classify`; return `{"doc_type": str}`
    - _Requirements: R3.1, R3.5_

  - [x] 13.4 Implement `GET /health` route
    - Return `{"status": "ok", "mistral_key_present": bool}` (check key presence without logging the value)
    - _Requirements: R10.1_

  - [ ]* 13.5 Write unit tests `test_invalid_file_type`, `test_file_too_large`, `test_health_endpoint`
    - `test_invalid_file_type`: POST a `.txt` file; assert 400 response
    - `test_file_too_large`: POST a synthetic payload > `max_upload_bytes`; assert 413 response
    - `test_health_endpoint`: GET `/health`; assert `{"status": "ok"}` when key is set
    - _Requirements: R1.2, R1.3, R10.1_

- [x] 14. Checkpoint — API layer complete
  - Ensure all unit tests pass: `pytest tests/unit/ -v`
  - Confirm `GET /health` returns 200 when `MISTRAL_API_KEY` is set in `.env`.

- [x] 15. Implement CSS and HTML template (`static/styles.css`, `templates/index.html`)
  - [x] 15.1 Write `static/styles.css` with NHAI color scheme
    - Navy `#003366` for header, primary buttons, and table headers
    - Saffron `#FF9933` for accent borders, focus rings, and active states
    - White background, dark grey (`#333`) body text
    - Single-column max-width layout (≤ 720 px); responsive for narrower viewports
    - Results card hidden by default (`display: none`); rejection banner hidden by default
    - Progress indicator hidden by default
    - _Requirements: R8.1, R8.3_

  - [x] 15.2 Write `templates/index.html` Jinja2 template
    - NHAI logo + title header with `[EN | हिं]` language toggle
    - PDF upload dropzone (`<input type="file" accept=".pdf">`)
    - Fields textarea with hint: "be specific — e.g. 'Agreement Date' not just 'Date'"
    - Extract button (`data-i18n="extract"`)
    - Rejection banner (`id="rejection-banner"`, hidden by default) with doc-type message and "Force Extract Anyway" button
    - Progress indicator (`id="progress"`, hidden by default)
    - Results card (`id="results-card"`, hidden by default) with field/value/source table, doc-type label, Download JSON button, Download CSV button
    - Load `static/js/*.js` as ES modules (`<script type="module">`)
    - All user-visible labels use `data-i18n` attributes for i18n support
    - _Requirements: R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R8.7_

- [ ] 16. Implement frontend ES modules (`static/js/`)
  - [x] 16.1 Implement `static/js/validation.js`
    - `export function validateFile(file)` — returns `null` (ok) or an error string; checks file is a PDF by MIME type and `.pdf` extension
    - `export function validateFields(fieldsText)` — returns `null` or error string; checks at least one non-empty field after splitting on commas/newlines
    - _Requirements: R1.2, R1.4, R8.1_

  - [x] 16.2 Implement `static/js/progress.js`
    - `export function showProgress(message)`, `hideProgress()`, `updateProgress(message)` — toggle `display` on `#progress` element
    - _Requirements: R8.4_

  - [x] 16.3 Implement `static/js/lang.js`
    - `const STRINGS = { en: {...}, hi: {...} }` covering all `data-i18n` keys used in `index.html` (upload, extract, fields_hint, processing, download_json, download_csv, force_extract, rejection_message, etc.)
    - `export function applyLanguage(lang)` — updates `textContent` of every `[data-i18n]` element
    - `export function getCurrentLang()` — returns current active language code
    - _Requirements: R8.2_

  - [x] 16.4 Implement `static/js/api.js`
    - `export async function postExtract(formData)` — POST to `/extract`; returns parsed JSON or `Blob` (for CSV)
    - `export async function postClassify(formData)` — POST to `/classify`; returns parsed JSON `{doc_type}`
    - Throw on non-OK HTTP status with the response body as the error message
    - _Requirements: R1.1, R3.1_

  - [x] 16.5 Implement `static/js/ui.js`
    - `export function showResultsCard(response)` — reveal `#results-card`, populate field/value/source table, set doc-type label
    - `export function hideResultsCard()` — hide `#results-card`
    - `export function showRejectionBanner(docType, onForceExtract)` — reveal `#rejection-banner`, set doc-type text, wire Force Extract button callback
    - `export function renderFieldTable(fieldNames, records)` — build `<tr>` rows for each field
    - `export function showErrorMessage(msg)` — display user-visible error
    - Wire form submit: run `validateFile` + `validateFields`; call `showProgress`; call `postExtract`; on rejection response call `showRejectionBanner`; on success call `showResultsCard`; always call `hideProgress`
    - Wire language toggle to call `applyLanguage`
    - Wire Force Extract button to re-submit with `force_extract=true`
    - Wire Download JSON / Download CSV buttons to trigger `Blob` download
    - _Requirements: R8.1, R8.2, R8.3, R8.4, R8.5, R8.6, R8.7_

- [x] 17. Checkpoint — frontend complete
  - Start the dev server manually (`uvicorn app:app --reload`) and verify `GET /` serves the page without JS console errors.

- [x] 18. Implement property-based tests (`tests/property/test_properties.py`)
  - [x] 18.1 Write `test_output_stability` — Property 1
    - Strategy: `ocr_text=st.text(min_size=50)`, `field_name=st.text(min_size=1, max_size=50).filter(str.strip)`; `max_examples=100`
    - Use `MockMistralClient` that returns a value present in the text on first call; assert second call (cache hit) returns identical `FieldExtraction`; assert result unchanged after extracting an unrelated field in between
    - **Property 1: Output Stability**
    - **Validates: Requirements R5.1, R5.2, R5.3, R5.4, R5.5**

  - [x] 18.2 Write `test_verbatim_grounding` — Property 2
    - Strategy: `ocr_text=st.text(min_size=20)`, `field_name=st.text(min_size=1, max_size=50)`; `max_examples=100`
    - Use `MockMistralClient(returns_arbitrary_values=True)` that may return values NOT in the text; assert if `result.value != "Null"` then `normalize_text(result.value) in normalize_text(ocr_text)`
    - **Property 2: Verbatim Grounding**
    - **Validates: Requirements R4.2, R4.6**

  - [x] 18.3 Write `test_output_schema_stability` — Property 3
    - Strategy: `field_names=st.lists(...)`, `records=st.lists(build_extraction_record_strategy(), ...)`; `max_examples=100`
    - Assert JSON output has keys `doc_type`, `field_names`, `records`; every record contains every requested field name; CSV columns are exactly `[source_file, *field_names, status, failure_reason]`; Hindi characters survive round-trip
    - **Property 3: Output Schema Stability**
    - **Validates: Requirements R7.1, R7.2, R7.3, R7.4, R7.6**

  - [x] 18.4 Write `test_classification_gate` — Property 4
    - Strategy: `ocr_text=st.text(min_size=10)`, `force_extract=st.booleans()`; `max_examples=100`
    - Use `MockClassifier(returns="other")`; when `force_extract=False` assert all records have `status="rejected"` and non-empty `failure_reason`; when `force_extract=True` assert no record has `status="rejected"`
    - **Property 4: Classification Gate**
    - **Validates: Requirements R3.3, R3.4**

  - [x] 18.5 Write `test_ocr_single_call_and_cache` — Property 5
    - Strategy: `ocr_text=st.text(min_size=50)`, `field_names=st.lists(st.text(min_size=1), min_size=2, max_size=8, unique=True)`; `max_examples=100`
    - Use `CountingMockOcr`; assert `ocr.call_count == 1` after pipeline run; add a duplicate field name (uppercase of first); assert LLM call count for that field is 1 (cache hit for duplicate)
    - **Property 5: OCR Single-Call Invariant and Stability Cache Hit Rate**
    - **Validates: Requirements R9.2, R9.3, R5.5**

- [x] 19. Implement unit tests (`tests/unit/`)
  - [x] 19.1 Write `test_normalize_fields` — deduplication
    - _Requirements: R1.5_

  - [x] 19.2 Write `test_grounding_check` — all four confidence levels
    - _Requirements: R4.7_

  - [x] 19.3 Write `test_ocr_fallback_trigger` and `test_ocr_error_fallback`
    - _Requirements: R2.3, R2.4_

  - [x] 19.4 Write `test_double_failure`
    - _Requirements: R2.5_

  - [x] 19.5 Write `test_pydantic_validation_retry`
    - _Requirements: R4.2_

  - [x] 19.6 Write `test_temperature_zero`
    - _Requirements: R5.6_

  - [x] 19.7 Write `test_invalid_file_type`, `test_file_too_large`, `test_health_endpoint`
    - _Requirements: R1.2, R1.3, R10.1_

  - [x] 19.8 Write `test_settings_missing_key`
    - _Requirements: R10.4_

  - [x] 19.9 Write `test_csv_unicode`
    - _Requirements: R7.6_

- [ ] 20. Implement integration / fixture tests (`tests/integration/`)
  - [~] 20.1 Add anonymized fixture PDFs to `tests/fixtures/` (LOA, financial closure, debarment, and a non-NHAI PDF — small, no real PII)
    - _Requirements: R4.3, R4.4, R3.3_

  - [~] 20.2 Write `test_loa_extraction_known_values`
    - Upload LOA fixture; assert known field values match expected strings; validates verbatim grounding on tabular document
    - _Requirements: R4.1, R4.2, R4.6_

  - [~] 20.3 Write `test_financial_closure_prose_values`
    - Upload financial closure fixture; assert values embedded in prose sentences (e.g. "Contract Value") are correctly extracted; validates semantic grounding fix for R4
    - _Requirements: R4.3, R4.4, R4.5_

  - [~] 20.4 Write `test_debarment_extraction`
    - Upload debarment fixture; assert name and PAN fields are found with non-Null values
    - _Requirements: R4.1, R3.1_

  - [~] 20.5 Write `test_other_document_rejected`
    - Upload non-NHAI PDF without `force_extract`; assert `status = "rejected"` and non-empty `failure_reason`
    - _Requirements: R3.3_

- [~] 21. Final checkpoint — all tests pass
  - Run `pytest tests/ -v` and ensure all non-optional tests pass.
  - Run `pytest tests/property/ -v` for property-based tests (requires live Mistral API or full mocks).
  - Ask the user if any issues arise before marking complete.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they include all unit, property, and integration test sub-tasks.
- Each task references specific requirements (R1–R10) for traceability. Requirement 11 is **DEFERRED** and not referenced.
- Checkpoints (tasks 12, 14, 17, 21) ensure incremental validation at meaningful boundaries.
- Property tests use `MockMistralClient` / `MockOcr` / `MockClassifier` stubs so they run without live API calls.
- Integration tests (task 20) require either live Mistral API credentials or pre-recorded VCR cassettes; commit only anonymized fixture PDFs with no real PII.
- The stability cache is per-`MistralExtractor` instance (not per-process), so each pipeline run gets a fresh extractor with an empty cache — PII is never retained across requests.
- `records_to_json` must set `ensure_ascii=False` to preserve Hindi characters.
- For CSV, use Python's `csv.writer` with `encoding="utf-8-sig"` (BOM) so Excel opens the file correctly.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2", "5.1", "9.1"] },
    { "id": 3, "tasks": ["5.2", "6.1", "7.1", "9.2", "10.1"] },
    { "id": 4, "tasks": ["8.1", "10.2"] },
    { "id": 5, "tasks": ["8.2", "8.3", "11.1"] },
    { "id": 6, "tasks": ["11.2"] },
    { "id": 7, "tasks": ["11.3", "13.1"] },
    { "id": 8, "tasks": ["13.2", "13.3", "13.4"] },
    { "id": 9, "tasks": ["13.5", "15.1"] },
    { "id": 10, "tasks": ["15.2", "16.1", "16.2", "16.3", "16.4"] },
    { "id": 11, "tasks": ["16.5"] },
    { "id": 12, "tasks": ["18.1", "18.2", "18.3", "18.4", "18.5", "19.1", "19.2", "19.3", "19.4", "19.5", "19.6", "19.7", "19.8", "19.9"] },
    { "id": 13, "tasks": ["20.1"] },
    { "id": 14, "tasks": ["20.2", "20.3", "20.4", "20.5"] }
  ]
}
```

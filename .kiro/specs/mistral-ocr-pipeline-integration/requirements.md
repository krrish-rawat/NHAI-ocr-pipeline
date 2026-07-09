# Requirements Document

## Introduction

The NHAI PDF Parser currently extracts structured fields from government PDFs by rendering every page to JPEG images and sending those images to Gemini. This approach is slow (15–20 s for 2–3 attributes) and expensive in API payload terms because images are re-encoded and re-transmitted on every call.

This feature replaces the image-only pipeline with a two-stage approach:
1. **Mistral OCR** pre-processes the PDF once into structured markdown/JSON text.
2. Gemini receives that clean text (instead of raw pixel images) for both the classification phase and the extraction phase.

An optional complementary optimisation — uploading files to the **Google Files API** once and referencing them by URI — is scoped out as a future concern; the Mistral OCR text path is sufficient to eliminate the bulk of image payload overhead and is the primary focus of this spec.

The Tesseract-based bounding-box index that drives `source_meta` / UI highlighting is preserved as-is, because it operates independently of what is sent to Gemini.

---

## Glossary

- **Pipeline**: The end-to-end flow from PDF upload → Phase 1 classification → Phase 2 extraction → JSON/CSV response.
- **Mistral_OCR_Client**: New service component responsible for calling the Mistral OCR API and returning structured text.
- **Extraction_Service**: Existing `ExtractionService` class in `extraction_service.py` that orchestrates Phase 1 and Phase 2.
- **LLM_Client**: Existing `GeminiExtractionClient` in `llm_client.py` that sends requests to Gemini.
- **PDF_Renderer**: Existing `PdfRenderer` class that renders pages to images and runs Tesseract OCR.
- **OCR_Index**: Cached per-document Tesseract word-level bounding-box data used exclusively for `source_meta` coordinates.
- **Source_Meta**: The `source_meta` JSON field returned per extracted attribute, containing `pageNumber`, `text`, `confidence`, and optional `bbox` / `bbox_lines` for UI highlighting.
- **Phase_1**: The quick document-classification step that determines whether a PDF is a valid NHAI document type before proceeding to full extraction.
- **Phase_2**: The full field-extraction step, only executed when Phase 1 passes.
- **Structured_Text**: The markdown or JSON text produced by Mistral OCR from a PDF — captures headings, tables, and body text in a machine-readable form.
- **Scanned_PDF**: A PDF whose pages consist of rasterised images with no native text layer (e.g. photographed paper documents).
- **Native_Text_PDF**: A PDF that contains an embedded text layer (e.g. digitally produced documents).
- **Settings**: The `AppSettings` dataclass in `settings.py` that reads configuration from environment variables.
- **GEMINI_API_KEY**: Existing environment variable for the Gemini API key.
- **MISTRAL_API_KEY**: New environment variable for the Mistral API key.

---

## Requirements

### Requirement 1: Mistral OCR Pre-Processing Step

**User Story:** As a developer operating the pipeline, I want the system to run Mistral OCR on an uploaded PDF once before any Gemini call, so that Gemini receives clean structured text instead of pixel images, reducing latency and improving extraction accuracy.

#### Acceptance Criteria

1. WHEN a PDF is submitted for extraction, THE Mistral_OCR_Client SHALL call the Mistral OCR API with the raw PDF bytes and return a single Structured_Text string (markdown or plain text) covering all pages, with page boundaries separated by newlines.
2. THE Mistral_OCR_Client SHALL accept both Scanned_PDFs and Native_Text_PDFs via the same `extract_text(pdf_path: str) -> str` method signature, producing Structured_Text in both cases without the caller needing to know the PDF type.
3. WHEN the Mistral OCR API call succeeds and returns Structured_Text with 50 or more characters, THE Extraction_Service SHALL pass that Structured_Text to both Phase_1 and Phase_2 Gemini prompts in place of page images.
4. THE Mistral_OCR_Client SHALL be called at most once per uploaded PDF file per request, with the resulting Structured_Text stored in a local variable and reused for Phase_1 and Phase_2 of that same request without a second API call.
5. IF the Mistral OCR API call fails with a network error, timeout, or authentication error, THEN THE Extraction_Service SHALL log a warning that includes the error type and message, then activate the image-based fallback path for that request without attempting any Gemini call on the OCR path.
6. IF the Mistral OCR API returns a response whose Structured_Text contains fewer than 50 characters, THEN THE Extraction_Service SHALL log a warning stating the returned character count and activate the image-based fallback path for that request without attempting any Gemini call on the OCR path; a logged warning alone without activating the fallback is not permitted.

---

### Requirement 2: Gemini Prompt Adaptation for Text Input

**User Story:** As a developer, I want the Gemini prompts to work correctly whether the input is structured text or images, so that classification and extraction quality is maintained or improved when switching input modalities.

#### Acceptance Criteria

1. WHEN Structured_Text is available, THE LLM_Client SHALL send the Structured_Text as a text part in the Gemini content array and SHALL NOT include any image parts in that request.
2. THE LLM_Client SHALL accept a `text_context: str | None` parameter on both `generate_json` and `generate_text` methods. WHEN `text_context` is a non-empty string, it SHALL be included as the first text part in the Gemini content array. WHEN `text_context` is `None` or an empty string, it SHALL NOT be added to the content array.
3. WHEN `text_context` is `None`, THE LLM_Client SHALL behave identically to the current image-based implementation, accepting and sending `images: list[Image.Image]` as before.
4. WHEN `text_context` is a non-empty string, THE LLM_Client SHALL NOT accept or send image parts, and the `images` parameter SHALL be ignored or absent.
5. THE Phase_1 classification prompt text SHALL contain the phrase "structured OCR text" to explicitly tell the model that the input is text, not an image scan.
6. THE Phase_2 extraction prompt produced by `build_dynamic_prompt` SHALL contain the phrase "structured OCR text" and SHALL instruct the model to ground extracted values against the provided text content.

---

### Requirement 3: Preservation of Source_Meta and Bounding-Box Highlighting

**User Story:** As a UI consumer, I want bounding-box coordinates in `source_meta` to remain accurate regardless of whether Gemini receives images or text, so that PDF highlighting in the browser is not broken.

#### Acceptance Criteria

1. THE PDF_Renderer SHALL continue to render pages to images and run Tesseract OCR to build the OCR_Index for every processed document when the Mistral OCR path is inactive. WHEN the Mistral OCR path is active and Mistral provides Structured_Text of sufficient quality, THE PDF_Renderer SHALL skip the Tesseract OCR step (image rendering for bbox lookup may still occur separately for Source_Meta purposes).
2. THE Extraction_Service SHALL continue to call `_build_bbox_for_source_text` using the Tesseract-derived OCR_Index to populate `bbox` and `bbox_lines` in Source_Meta for every extracted attribute.
3. WHEN the Mistral OCR path is active, THE Source_Meta `text` field SHALL still contain the verbatim `source_text` phrase returned by Gemini, and `pageNumber` SHALL be the result of the Tesseract-based fuzzy search — unchanged in behaviour.
4. THE Extraction_Service SHALL not remove, replace, or disable the `_get_or_build_ocr_index` call or the `_coerce_source_meta` call as part of this change.

---

### Requirement 4: Two-Phase Flow Preservation

**User Story:** As a product owner, I want the validate-then-extract two-phase flow to be preserved, so that invalid NHAI documents are still rejected cheaply before triggering a full extraction call.

#### Acceptance Criteria

1. WHEN a PDF is processed, THE Extraction_Service SHALL execute Phase_1 classification before Phase_2 extraction, as it does today.
2. IF Phase_1 determines the document type is not in the accepted whitelist, THEN THE Extraction_Service SHALL return the blocked response immediately without calling Mistral OCR for Phase_2 extraction text or calling Gemini for Phase_2 extraction.
3. THE Mistral_OCR_Client SHALL be invoked once before Phase_1, and its Structured_Text SHALL be reused in Phase_2, so that Mistral OCR is called exactly once per document regardless of which phases execute or how many attributes are requested. IF Phase_1 is bypassed, THE Mistral_OCR_Client SHALL still be called exactly once before Phase_2.
4. THE Extraction_Service SHALL preserve the `document_validity` response shape — containing `is_valid`, `detected_type`, `confidence`, and `message` — in all response paths.

---

### Requirement 5: Configuration and API Key Management

**User Story:** As an operator, I want the Mistral API key and OCR behaviour to be configurable via environment variables, so that I can manage credentials and toggle the feature without code changes.

#### Acceptance Criteria

1. THE Settings SHALL read a `MISTRAL_API_KEY` environment variable and expose it as `mistral_api_key: str | None` with a default of `None`.
2. THE Settings SHALL read a `USE_MISTRAL_OCR` environment variable and expose it as `use_mistral_ocr: bool`, defaulting to `True` when `MISTRAL_API_KEY` is set and `False` otherwise.
3. WHEN `use_mistral_ocr` is `False` or `mistral_api_key` is `None`, THE Extraction_Service SHALL use the existing image-based pipeline without any behaviour change. IF the existing image-based pipeline is itself unavailable or raises an unhandled exception, THE Extraction_Service SHALL fail the extraction operation and return an error record rather than silently returning empty results.
4. THE Settings SHALL read a `MISTRAL_OCR_MODEL` environment variable and expose it as `mistral_ocr_model: str`, defaulting to `"mistral-ocr-latest"`.
5. THE Settings SHALL preserve all existing environment variables (`GEMINI_MODEL`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `MAX_UPLOAD_BYTES`, `EXTRACTION_RETRIES`, `SUMMARY_TIMEOUT_SECONDS`) with their current defaults unchanged.

---

### Requirement 6: Mistral OCR Client Implementation

**User Story:** As a developer, I want a dedicated, testable `MistralOcrClient` service class, so that Mistral API concerns are isolated from orchestration and Gemini concerns.

#### Acceptance Criteria

1. THE Mistral_OCR_Client SHALL be implemented as a class named `MistralOcrClient` in a new file `src/services/mistral_ocr_client.py`, following the existing service module pattern (dataclass or `__init__`-based, with a module-level logger).
2. THE Mistral_OCR_Client SHALL expose a public method `extract_text(pdf_path: str) -> str` that opens the file at `pdf_path`, calls the Mistral OCR API, and returns the concatenated Structured_Text for all pages joined by newlines.
3. THE Mistral_OCR_Client SHALL import and use the `mistralai` Python SDK to make API calls; the import SHALL be a top-level import inside `extract_text` (lazy), not at module level.
4. IF `import mistralai` raises `ImportError`, THEN THE `extract_text` method SHALL re-raise an `ImportError` whose message contains both the package name (`mistralai`) and the install instruction (`pip install mistralai`); authentication errors, network errors, and API-level errors SHALL raise non-ImportError exceptions that propagate to the caller.
5. WHEN `extract_text` completes successfully, THE method SHALL log at DEBUG level a message containing the number of pages returned by the API and the total character count of the returned Structured_Text.
6. WHEN `settings.use_mistral_ocr` is `True` and `settings.mistral_api_key` is not `None`, THE `build_extraction_service` factory function SHALL instantiate `MistralOcrClient` with `settings.mistral_api_key` and `settings.mistral_ocr_model`, and inject it into `ExtractionService`. WHEN `settings.use_mistral_ocr` is `True` but `settings.mistral_api_key` is `None`, the factory SHALL raise a `ValueError` with a message stating that `MISTRAL_API_KEY` must be set when `USE_MISTRAL_OCR` is enabled.

---

### Requirement 7: Output Format Preservation

**User Story:** As an API consumer, I want the JSON and CSV response shapes to remain identical after this change, so that no downstream integrations break.

#### Acceptance Criteria

1. THE Extraction_Service SHALL return JSON responses that contain the top-level keys `attributes` and `records` in all success paths. The `document_validity` key SHALL be present when a validity check was performed, matching the existing conditional behaviour in `app.py`.
2. WHEN output format is CSV, THE `records_to_csv` serializer SHALL produce columns in the order: `source_file`, then each requested attribute in the order they appear in the `attributes` list, then `status`, then `failure_reason`; the `source_meta` object SHALL NOT appear as a CSV column.
3. THE `records` array SHALL contain per-record objects with the keys `source_file`, one key per requested attribute (value as string), `source_meta`, `status`, and `failure_reason` — identical to the current implementation regardless of which input path (Mistral OCR or image) was used.
4. THE `source_meta` object per attribute SHALL be produced by `SourceMeta.to_dict()` and SHALL contain `pageNumber` (int), `text` (str), and `confidence` (str); it SHALL additionally contain `bbox` (list) and `bbox_lines` (list) when the Tesseract fuzzy-match succeeds, matching the current conditional logic in `SourceMeta.to_dict()`.

---

### Requirement 8: Performance Target

**User Story:** As a user uploading NHAI PDFs, I want field extraction to complete faster than the current pipeline, so that I can work more efficiently.

#### Acceptance Criteria

1. WHEN the Mistral OCR path is active and `MISTRAL_API_KEY` is configured, THE `extract_file_records` call (excluding HTTP upload time) SHALL complete Phase_1 + Phase_2 extraction for a single PDF with 5–7 requested attributes in 10 seconds or less under normal API response conditions.
2. WHEN the Mistral OCR path is active and Mistral OCR returns valid Structured_Text, THE Extraction_Service SHALL NOT call `render_to_images` for the purpose of sending images to Gemini; image rendering SHALL only occur if needed for Tesseract bbox computation.
3. WHEN the Mistral OCR path is active and the Mistral API call or the Mistral response validation fails, THE Extraction_Service SHALL activate the image-based fallback path as specified in Requirement 1.5–1.6 — image rendering for Gemini SHALL occur only on this fallback path.
4. THE Mistral_OCR_Client SHALL enforce an 8-second timeout on the Mistral OCR API call; IF the call does not complete within 8 seconds, it SHALL raise a `TimeoutError` that the Extraction_Service treats as an OCR failure, activating the image-based fallback.

---

### Requirement 9: Dependency Management

**User Story:** As a developer maintaining the project, I want all new dependencies to be declared with minimum-version constraints in `requirements.txt`, so that the environment is reproducible and upgradeable.

#### Acceptance Criteria

1. THE `requirements.txt` SHALL declare `mistralai>=1.0.0` as a new entry; existing entries SHALL remain unchanged.
2. WHEN `USE_MISTRAL_OCR` is not set or is `False`, THE application SHALL start and serve requests successfully even if the `mistralai` package is not installed, because the import of `mistralai` occurs inside `MistralOcrClient.extract_text` at call time, not at module import time.
3. THE `requirements.txt` SHALL preserve all existing dependencies (`pydantic`, `pandas`, `python-dotenv`, `fastapi`, `uvicorn[standard]`, `python-multipart`, `jinja2`, `google-generativeai`, `PyMuPDF`, `Pillow`, `openpyxl`, `pytesseract`, `rapidfuzz`) with their current version constraints unchanged.

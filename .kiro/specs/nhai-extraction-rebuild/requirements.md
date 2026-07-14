# Requirements Document

## Introduction

This document specifies requirements for a clean, production-quality rebuild of the **NHAI PDF Data Extraction** tool. The tool lets an operator upload official National Highways Authority of India (NHAI) PDF documents, specify which fields to extract, and receive stable structured output (JSON/CSV) with each field's value grounded in verbatim source text.

The rebuild keeps the proven pipeline from the prototype — PDF upload → OCR to structured text → Phase 1 classify/gate → Phase 2 grounded extraction → structured output — while fixing reliability, output-stability, and user-experience problems. The single most important improvement is **output stability**: adding a field to a re-run must never perturb the values of previously extracted fields.

This is a single-user internal tool. Authentication, user accounts, persistence/database, multi-tenancy, deployment/infrastructure, and rate limiting are explicitly **out of scope** for this spec.

> **Deferred scope note:** **Requirement 11: Document-Type Field Schemas and Field Alignment** is currently **DEFERRED (On Hold)** and is **not in scope for the current build**. It is retained below in full for future implementation, pending confirmation of the canonical extractable field set for each document type. The design and task phases for the current build SHALL NOT implement Requirement 11.

### Runtime stack (fixed, not under design)

- Backend: Python + FastAPI, Jinja2 templates
- Frontend: vanilla HTML/CSS/JS (no framework)
- OCR: Mistral OCR (PDF → structured markdown text), PDF sent inline as base64 data URI in a single API call
- LLM extraction: Mistral chat models (a small model for classification, a large model for extraction)
- A single Mistral API key serves both OCR and LLM calls

## Glossary

- **System**: The complete NHAI PDF Data Extraction tool (backend + frontend).
- **Backend**: The FastAPI application that orchestrates the extraction pipeline and serves the API and templates.
- **Web_UI**: The vanilla HTML/CSS/JS single-page frontend served to the operator.
- **Operator**: The single human user who uploads documents and requests field extraction.
- **OCR_Service**: The component that converts an uploaded PDF into structured markdown text via Mistral OCR.
- **Classifier**: The Phase 1 component that assigns a document type to the OCR text using the small Mistral chat model.
- **Extractor**: The Phase 2 component that extracts requested fields from the OCR text using the large Mistral chat model.
- **Serializer**: The component that renders extraction results into JSON and CSV output.
- **Configuration_Loader**: The component that reads the Mistral API key and model names from environment variables.
- **Field**: A named attribute the Operator requests (e.g. "Name", "Date of Birth", "PAN", "Agreement Date").
- **Field_Value**: The extracted value for a Field, or the literal string "Null" when no grounded value is found.
- **Source_Text**: The shortest verbatim (or near-verbatim) phrase or sentence from the OCR text that states a Field_Value and, by its meaning or surrounding context, supports the Field. The Source_Text does not need to contain an explicit adjacent label for the Field.
- **Grounding**: The rule combining a hard condition and a soft condition. The hard condition (verbatim presence) requires that every non-Null Field_Value appear verbatim in the OCR text; if the value is not present in the text, the Field_Value is "Null". The soft condition (semantic support) allows the Field to be identified from the meaning of the surrounding sentence or context rather than from an explicit adjacent label.
- **Accepted_Document_Type**: One of: Letter of Award (LOA), Completion Certificate (CC), Provisional Completion Certificate (PCC), Financial Closure, Debarment/Blacklisting/Restriction-from-participation records.
- **Other_Document**: A document classified as not being any Accepted_Document_Type.
- **Force_Extract**: An Operator override that runs extraction on a document even when the Classifier classifies it as an Other_Document.
- **Extraction_Request**: A single invocation consisting of one uploaded document and an ordered set of requested Fields.
- **Output_Record**: The structured result for one document/row, containing `source_file`, one column per requested Field, `status`, and `failure_reason`.
- **Output_Stability**: The property that, for the same document and the same OCR text, the Field_Value returned for any given Field depends only on that Field (and the document), not on which other Fields are requested in the same Extraction_Request.
- **Document_Type_Schema**: The canonical set of standard extractable Fields defined for a single Accepted_Document_Type, used to suggest default selectable Fields for a classified document.
- **Custom_Field**: A Field explicitly added by the Operator that is not part of the classified document type's Document_Type_Schema, requested for one-off extraction.
- **Alignment_Warning**: A non-blocking notice raised when the Operator requests one or more Fields that are neither part of the classified document type's Document_Type_Schema nor explicitly-added Custom_Fields, indicating those Fields may not belong to this document type.

## Requirements

### Requirement 1: PDF Upload and Validation

**User Story:** As an Operator, I want to upload an NHAI PDF and specify the fields to extract, so that I can obtain structured data without manual reading.

#### Acceptance Criteria

1. WHEN the Operator submits an Extraction_Request with a PDF file and one or more Fields, THE Backend SHALL accept the request and begin the extraction pipeline.
2. IF the uploaded file is not a PDF (by content type or file signature), THEN THE Backend SHALL reject the request and return an error message identifying the file as an unsupported type.
3. IF the uploaded file size exceeds the configured maximum upload size, THEN THE Backend SHALL reject the request and return an error message stating the maximum allowed size.
4. IF the Extraction_Request contains zero Fields after normalization, THEN THE Backend SHALL reject the request and return an error message requesting at least one Field.
5. WHEN the Operator supplies Fields containing duplicate names differing only by surrounding whitespace or letter case, THE Backend SHALL deduplicate the Fields into a single normalized set while preserving the Operator-provided order of first occurrence.

### Requirement 2: OCR Text Conversion with Fallback

**User Story:** As an Operator, I want scanned bilingual PDFs converted to structured text reliably, so that extraction works on real NHAI documents.

#### Acceptance Criteria

1. WHEN a valid PDF is accepted, THE OCR_Service SHALL convert the PDF into structured markdown text using a single Mistral OCR call with the PDF sent inline as a base64 data URI.
2. THE OCR_Service SHALL process documents that contain both English and Hindi content.
3. IF the OCR text produced for a document is shorter than the configured minimum text length, THEN THE OCR_Service SHALL treat the text-first path as failed and invoke the image-based fallback path.
4. IF the Mistral OCR call fails or returns an error, THEN THE OCR_Service SHALL invoke the image-based fallback path rather than aborting the Extraction_Request.
5. IF both the text-first path and the fallback path fail, THEN THE Backend SHALL return an Output_Record with `status` set to failure and a `failure_reason` describing the OCR failure.

### Requirement 3: Document Classification and Gate (Phase 1)

**User Story:** As an Operator, I want non-NHAI documents rejected before extraction, so that I do not waste time and cost on irrelevant files.

#### Acceptance Criteria

1. WHEN OCR text is available for a document, THE Classifier SHALL assign exactly one document type from the set of Accepted_Document_Types plus "other".
2. IF the Classifier assigns a type within the Accepted_Document_Types, THEN THE Backend SHALL proceed to Phase 2 extraction.
3. IF the Classifier classifies the document as an Other_Document AND Force_Extract is not enabled, THEN THE Backend SHALL block extraction and return a result indicating the document was rejected as an unrecognized type.
4. WHERE Force_Extract is enabled for an Extraction_Request, THE Backend SHALL proceed to Phase 2 extraction even when the document is classified as an Other_Document.
5. THE Backend SHALL include the assigned document type in the response for every Extraction_Request that reaches the Classifier.

### Requirement 4: Grounded Field Extraction (Phase 2)

**User Story:** As an Operator, I want each requested field matched to the value in the source text — whether that value sits next to an explicit label (tabular documents) or is embedded in a sentence (prose documents) — so that extracted values are accurate, present in the document, and never fabricated or borrowed from a clause about a different field.

#### Acceptance Criteria

1. WHEN Phase 2 runs for an Extraction_Request, THE Extractor SHALL return a Field_Value and a Source_Text for every requested Field.
2. IF the extracted Field_Value does not appear verbatim in the OCR text, THEN THE Extractor SHALL return the Field_Value "Null" AND the Source_Text "Null" for that Field, rather than an inferred, fabricated, or guessed value.
3. WHERE a Field's value is not adjacent to an explicit label in the OCR text, THE Extractor SHALL identify the Field semantically from the meaning of the surrounding sentence or context, and SHALL return the exact source sentence or phrase that states the value as the Source_Text.
4. THE Extractor SHALL NOT assign a Field a value whose surrounding context clearly describes a different field.
5. IF the only candidate value for a Field appears in a sentence or clause whose context clearly describes a different field, THEN THE Extractor SHALL return "Null" for that Field rather than borrowing the mismatched value.
6. WHEN a Field_Value is returned as non-Null, THE Extractor SHALL return a Source_Text that is verbatim or near-verbatim from the OCR text, where "near-verbatim" means the Source_Text differs from the document text only in normalized whitespace, letter case, or punctuation, with no words added, removed, or reordered.
7. THE Backend SHALL assign each Field a grounding confidence of "high" when the normalized Field_Value appears as a contiguous substring of the normalized Source_Text, "medium" when every token of the normalized Field_Value appears in the normalized Source_Text but not contiguously, and "low" when one or more tokens of a non-Null Field_Value are absent from the Source_Text.
8. WHEN a date value appears in the document, THE Extractor SHALL preserve the value's format exactly as written, without reformatting, reordering, or converting it, and SHALL return compound date values (multiple dates joined in one clause) as the full joined string including the joining text exactly as it appears.

### Requirement 5: Output Stability Across Re-Runs (Critical Correctness Property)

**User Story:** As an Operator, I want previously extracted field values to stay identical when I re-run extraction with one additional field, so that adding a field never silently changes results I already trusted.

#### Acceptance Criteria

1. WHEN the Operator runs an Extraction_Request for a set of Fields and later runs a second Extraction_Request on the same document (identical OCR text) for a superset of those Fields, THE Extractor SHALL return, for every Field common to both requests, a Field_Value that is character-for-character identical to the Field_Value returned in the first request, where "identical" means equal as strings including identical whitespace, letter case, punctuation, and the literal string "Null" where applicable.
2. THE Extractor SHALL produce, for a given Field, a Field_Value and Source_Text determined solely by that Field's normalized name and the document's OCR text, and the presence, absence, count, or ordering of any other requested Fields in the same Extraction_Request SHALL NOT alter that Field_Value or its Source_Text.
3. WHEN the same Field is extracted from the same OCR text more than once, THE Extractor SHALL return a Field_Value and Source_Text that are character-for-character identical on every extraction.
4. WHEN the Operator submits a Field whose normalized name is identical across two Extraction_Requests on the same document, THE Extractor SHALL return a character-for-character identical Field_Value and Source_Text in both responses.
5. WHEN the Extractor first computes a Field_Value and Source_Text for a given Field from a document's OCR text, THE Extractor SHALL store the result keyed by the document's OCR-text hash and the normalized Field name, and SHALL return the stored result unchanged for any subsequent extraction of the same key rather than re-invoking the extraction model.
6. THE Extractor SHALL invoke the Mistral extraction model with deterministic decoding settings (temperature set to 0) for every Field extraction.
7. IF two extractions of the same Field from the same OCR text produce Field_Values or Source_Texts that are not character-for-character identical, THEN THE Backend SHALL treat this as a correctness failure, and automated tests SHALL detect it by extracting each (document, Field) pair at least 3 times and asserting identical Field_Value and Source_Text across all repetitions.

### Requirement 6: Field Ambiguity Handling

**User Story:** As an Operator, I want help when a document contains many similar values, so that I can disambiguate which instance I need.

#### Acceptance Criteria

1. WHERE the Web_UI presents the field-entry interface, THE Web_UI SHALL display guidance advising the Operator to name Fields specifically (for example, distinguishing "Agreement Date" from "Completion Date").
2. WHERE the Operator enables an extract-all-instances mode for a Field, THE Extractor SHALL return every labeled instance of that Field found in the document, each with its own Source_Text.
3. WHEN extract-all-instances mode returns more than one instance for a Field, THE Backend SHALL include distinguishing context (the labeling clause) for each instance in the response.
4. WHEN a document lists multiple rows for the same entity type in a table, THE Extractor SHALL return one Output_Record per row, applying shared header context to every row.

### Requirement 7: Stable Output Schema (JSON and CSV)

**User Story:** As a downstream consumer, I want a stable output schema, so that I can rely on the structure across documents and runs.

#### Acceptance Criteria

1. THE Serializer SHALL produce CSV output whose columns are, in order: `source_file`, one column per requested Field in the requested order, `status`, and `failure_reason`.
2. THE Serializer SHALL produce JSON output containing the ordered list of requested Fields and a list of Output_Records.
3. WHEN a Field has no grounded value in an Output_Record, THE Serializer SHALL emit the Field_Value "Null" for that Field rather than omitting the column.
4. THE Serializer SHALL include a `status` value and, on failure, a non-empty `failure_reason` in every Output_Record.
5. WHEN the CSV output is parsed and then re-serialized with the same Field set, THE Serializer SHALL produce column headers and per-row Field columns identical to the original (schema round-trip stability).
6. THE Serializer SHALL preserve English and Hindi characters in both JSON and CSV output without corruption.

### Requirement 8: User Experience and Interface

**User Story:** As an Operator, I want a clean, uncluttered government-styled interface with clear status, so that I can extract fields confidently.

#### Acceptance Criteria

1. THE Web_UI SHALL present a single-column, government-styled layout for upload, field entry, and results.
2. WHERE the Operator toggles the language control, THE Web_UI SHALL switch all interface labels between English and Hindi.
3. WHILE no extraction result is available, THE Web_UI SHALL keep the results card hidden.
4. WHILE an Extraction_Request is in progress, THE Web_UI SHALL display a progress indication.
5. WHEN extraction completes, THE Web_UI SHALL reveal the results card containing the extracted Fields and their values.
6. IF the document is classified as an Other_Document, THEN THE Web_UI SHALL display an invalid-document warning banner offering a Force_Extract override control.
7. WHEN the Operator activates the Force_Extract override, THE Web_UI SHALL resubmit the Extraction_Request with Force_Extract enabled.

### Requirement 9: Performance

**User Story:** As an Operator, I want single-document extraction to be fast, so that the tool stays responsive during routine work.

#### Acceptance Criteria

1. WHEN the Operator submits an Extraction_Request for a single document requesting 5 to 7 Fields under normal operating conditions, THE Backend SHALL return a result within 10 seconds.
2. THE OCR_Service SHALL convert each document to text using a single OCR call rather than repeated per-page image calls on the text-first path.
3. WHEN multiple Fields are requested for one document, THE Backend SHALL reuse the document's OCR text across all Field extractions within that Extraction_Request rather than re-running OCR per Field.

### Requirement 10: Configuration

**User Story:** As an Operator, I want the API key and model names configurable via environment variables, so that I can run the tool without code changes and without authentication.

#### Acceptance Criteria

1. THE Configuration_Loader SHALL read the Mistral API key from an environment variable.
2. THE Configuration_Loader SHALL read the OCR model name, the classification model name, and the extraction model name from environment variables, each with a documented default.
3. THE Configuration_Loader SHALL read the maximum upload size from an environment variable with a documented default.
4. IF the Mistral API key is absent at startup, THEN THE Backend SHALL report a clear configuration error identifying the missing environment variable.
5. THE System SHALL operate without any authentication, user accounts, or login step.

### Requirement 11: Document-Type Field Schemas and Field Alignment

> **Status: DEFERRED (On Hold)** — Not in scope for the current build. Retained for future implementation pending confirmation of the canonical extractable field set for each document type. Design and task phases for the current build SHALL NOT implement this requirement.

**User Story:** As an Operator, I want each document type to suggest its own standard fields and warn me when I request fields that do not belong to that type, so that I extract the right fields for the document without being blocked when I intentionally ask for something different.

#### Acceptance Criteria

1. THE System SHALL define a Document_Type_Schema for each Accepted_Document_Type (LOA, CC, PCC, Financial Closure, Debarment), enumerating the standard extractable Fields for that type.
2. WHEN a document is classified as an Accepted_Document_Type, THE Web_UI SHALL offer the Fields of that type's Document_Type_Schema to the Operator as default selectable Fields.
3. THE Operator SHALL be able to add one or more Custom_Fields beyond the classified document type's Document_Type_Schema for one-off extraction.
4. WHEN the Operator requests one or more Fields that are neither part of the classified document type's Document_Type_Schema nor explicitly-added Custom_Fields, THE Backend SHALL surface a non-blocking Alignment_Warning identifying those Fields as possibly not belonging to this document type.
5. WHEN an Alignment_Warning is surfaced, THE Backend SHALL proceed with extraction for all requested Fields without blocking the Extraction_Request.
6. THE Backend SHALL derive the Alignment_Warning solely from comparison between the requested Fields and the classified document type's Document_Type_Schema, and SHALL NOT use a Field_Value of "Null" as a signal of field-to-document-type mismatch.
7. WHERE a requested Field is a Custom_Field, THE Backend SHALL exclude that Field from the Alignment_Warning.

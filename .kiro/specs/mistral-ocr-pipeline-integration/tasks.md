# Implementation Plan: Mistral OCR Pipeline Integration

## Overview

Replace the image-heavy Gemini extraction pipeline with a text-first approach using Mistral OCR. The implementation follows a bottom-up approach: configuration first, then the new client, then adapting existing services, and finally wiring it all together.

## Tasks

- [x] 1. Add Mistral configuration fields to `src/services/settings.py`: add `mistral_api_key`, `mistral_ocr_model`, and `use_mistral_ocr` fields reading from environment variables with appropriate defaults (R5)
- [x] 2. Create `src/services/mistral_ocr_client.py` with `MistralOcrClient` class implementing `extract_text(pdf_path: str) -> str` using lazy import of `mistralai`, Mistral upload→signed-URL→OCR flow, 8s timeout, and DEBUG logging of page count and char count (R1, R6, R8)
- [x] 3. Add `mistralai>=1.0.0` to `requirements.txt` without modifying existing entries (R9)
- [x] 4. Add `text_context: str | None = None` parameter to `GeminiExtractionClient.generate_json()` and `generate_text()` in `src/services/llm_client.py`; when set, send text-only content instead of images (R2)
- [x] 5. Create text-based prompt variants in `src/services/extraction_service.py`: `CLASSIFICATION_PROMPT_TEXT` and `build_dynamic_prompt_text(attributes)` containing "structured OCR text" and retaining all grounding rules (R2)
- [x] 6. Add `mistral_ocr: MistralOcrClient | None = None` field to `ExtractionService` dataclass and update `extract_file_records` to call Mistral OCR once before Phase 1, store result, use text_context for both phases, fall back to images on failure or <50 chars (R1, R3, R4, R7, R8)
- [x] 7. Update `build_extraction_service()` factory to instantiate and inject `MistralOcrClient` when `settings.use_mistral_ocr` is True and key is set; raise `ValueError` if key is missing but feature is on (R5, R6)
- [x] 8. Add `MISTRAL_API_KEY` documentation to `.env` example comments so operators know which variables to configure (R5)
- [x] 9. End-to-end verification: test valid NHAI PDF completes in ≤10s with 5-7 attrs, invalid PDF is blocked, fallback works with bad key, source_meta/bbox still populated, JSON/CSV shapes unchanged (R1, R3, R7, R8)

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": [1, 2, 3, 4]},
    {"wave": 2, "tasks": [5, 6, 7]},
    {"wave": 3, "tasks": [8]},
    {"wave": 4, "tasks": [9]}
  ]
}
```

- **Wave 1** (parallel): Settings, MistralOcrClient, requirements.txt, LLM Client text_context
- **Wave 2** (depends on wave 1): Prompt variants, orchestration, factory
- **Wave 3** (depends on wave 2): Env documentation
- **Wave 4** (depends on all): End-to-end verification

## Notes

- Tesseract OCR for bbox continues to run regardless of which path is active — it's independent
- The lazy import of `mistralai` means the app starts fine without the package when the feature is off
- The image-based fallback is automatic and seamless; no user intervention needed if Mistral fails

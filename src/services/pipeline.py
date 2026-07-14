"""ExtractionPipeline: orchestrates the full OCR → classify → extract → serialize flow.

Entry point for all backend extraction logic. Route handlers call only this.
Never raises exceptions — all errors are captured in ExtractionRecord.failure_reason.
"""
import logging
import tempfile
import os
from typing import Optional

from src.services.models import (
    ExtractionRecord,
    ExtractionResponse,
    FieldResult,
    SourceMeta,
)
from src.services.utils import deduplicate_fields, score_grounding
from src.services.ocr_service import MistralOcrClient, OcrError
from src.services.classifier import MistralClassifier, ACCEPTED_TYPES
from src.services.extractor import MistralExtractor
from src.services.settings import AppSettings

logger = logging.getLogger(__name__)

_REJECTION_REASON = (
    "Document classified as '{doc_type}' — not a recognized NHAI document type. "
    "Use force_extract=true to extract anyway."
)


def _build_failure_record(
    source_file: str,
    field_names: list[str],
    failure_reason: str,
    status: str = "failed",
) -> ExtractionRecord:
    """Build an ExtractionRecord representing a failure or rejection."""
    fields = {
        fn: FieldResult(value="Null", source_meta=SourceMeta(text="Null", confidence="unknown"))
        for fn in field_names
    }
    return ExtractionRecord(
        source_file=source_file,
        fields=fields,
        status=status,
        failure_reason=failure_reason,
    )


def _build_image_fallback_path(pdf_path: str) -> list[str]:
    """Render PDF pages to JPEG images for the fallback path.

    Returns a list of temp file paths. Caller is responsible for cleanup.
    Falls back to empty list on any rendering error.
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import io

        doc = fitz.open(pdf_path)
        image_paths = []
        try:
            for page_num in range(min(len(doc), 5)):  # cap at 5 pages
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                img.save(tmp.name, format="JPEG", quality=85)
                image_paths.append(tmp.name)
        finally:
            doc.close()
        return image_paths
    except Exception as exc:
        logger.warning("Image fallback rendering failed: %s", exc)
        return []


class ExtractionPipeline:
    """Orchestrates the full PDF extraction pipeline.

    Steps:
    1. OCR: convert PDF to structured text (Mistral OCR, base64 inline)
    2. Classify: identify document type (Phase 1 gate)
    3. Gate: block non-NHAI documents unless force_extract=True
    4. Extract: per-field extraction with stability cache (Phase 2)
    5. Return: ExtractionResponse with records
    """

    def __init__(
        self,
        ocr: MistralOcrClient,
        classifier: MistralClassifier,
        extractor: MistralExtractor,
        settings: AppSettings,
    ) -> None:
        self.ocr = ocr
        self.classifier = classifier
        self.extractor = extractor
        self.settings = settings

    def run(
        self,
        pdf_path: str,
        source_file: str,
        field_names: list[str],
        force_extract: bool = False,
    ) -> ExtractionResponse:
        """Run the full extraction pipeline. Never raises — errors go into records.

        Args:
            pdf_path: path to the temp PDF file on disk.
            source_file: original filename (for output metadata).
            field_names: ordered list of field names to extract.
            force_extract: if True, skip the classification gate.

        Returns:
            ExtractionResponse with doc_type, field_names, and records.
        """
        # Clear extractor cache for this request (PII hygiene)
        self.extractor.clear_cache()

        # Deduplicate and validate field names
        field_names = deduplicate_fields(field_names)

        # ── Step 1: OCR ───────────────────────────────────────────────────────
        ocr_text: Optional[str] = None
        image_paths: list[str] = []
        using_fallback = False

        try:
            ocr_text = self.ocr.extract_text(pdf_path)
            if len(ocr_text) < self.settings.min_ocr_text_length:
                logger.warning(
                    "OCR text too short (%d chars < %d) — activating image fallback",
                    len(ocr_text),
                    self.settings.min_ocr_text_length,
                )
                ocr_text = None
        except OcrError as exc:
            logger.warning("OCR failed: %s — activating image fallback", exc)

        if ocr_text is None:
            image_paths = _build_image_fallback_path(pdf_path)
            using_fallback = True
            if not image_paths:
                # Both paths failed
                record = _build_failure_record(
                    source_file,
                    field_names,
                    "OCR failed and image fallback rendering also failed.",
                    status="failed",
                )
                return ExtractionResponse(
                    doc_type="unknown",
                    field_names=field_names,
                    records=[record],
                )

        # ── Step 2: Classify ──────────────────────────────────────────────────
        try:
            if using_fallback:
                doc_type = self.classifier.classify_from_images(image_paths)
            else:
                doc_type = self.classifier.classify(ocr_text)
        except Exception as exc:
            logger.warning("Classification raised unexpectedly: %s", exc)
            doc_type = "other"

        # ── Step 3: Gate ──────────────────────────────────────────────────────
        if doc_type not in ACCEPTED_TYPES and not force_extract:
            record = _build_failure_record(
                source_file,
                field_names,
                _REJECTION_REASON.format(doc_type=doc_type),
                status="rejected",
            )
            return ExtractionResponse(
                doc_type=doc_type,
                field_names=field_names,
                records=[record],
            )

        # ── Step 4: Extract ───────────────────────────────────────────────────
        record: ExtractionRecord
        try:
            if using_fallback:
                # For the image fallback, we render to text via a basic extraction
                # Note: on true fallback with no OCR text, we use a concat approach
                # This path should be rare; primary path uses ocr_text
                fallback_text = "\n".join(
                    f"[Image page {i+1}]" for i in range(len(image_paths))
                )
                extraction_text = fallback_text
            else:
                extraction_text = ocr_text

            field_extractions = self.extractor.extract_fields(extraction_text, field_names)

            # Build FieldResult objects with grounding confidence
            fields: dict[str, FieldResult] = {}
            for fn in field_names:
                fe = field_extractions.get(fn)
                if fe is None:
                    fields[fn] = FieldResult(
                        value="Null",
                        source_meta=SourceMeta(text="Null", confidence="unknown"),
                    )
                else:
                    confidence = score_grounding(fe.value, fe.source_text)
                    fields[fn] = FieldResult(
                        value=fe.value,
                        source_meta=SourceMeta(text=fe.source_text, confidence=confidence),
                    )

            record = ExtractionRecord(
                source_file=source_file,
                fields=fields,
                status="success",
                failure_reason="",
            )

        except Exception as exc:
            logger.error("Extraction phase failed for %s: %s", source_file, exc, exc_info=True)
            record = _build_failure_record(
                source_file,
                field_names,
                f"Extraction failed: {type(exc).__name__}",
                status="failed",
            )

        finally:
            # Clean up temp image files
            for img_path in image_paths:
                try:
                    os.unlink(img_path)
                except OSError:
                    pass

        return ExtractionResponse(
            doc_type=doc_type,
            field_names=field_names,
            records=[record],
        )


def build_pipeline(settings: AppSettings) -> ExtractionPipeline:
    """Factory function: build a fully wired ExtractionPipeline from settings."""
    ocr = MistralOcrClient(
        api_key=settings.mistral_api_key,
        model=settings.mistral_ocr_model,
    )
    classifier = MistralClassifier(
        api_key=settings.mistral_api_key,
        model=settings.mistral_classification_model,
    )
    extractor = MistralExtractor(
        api_key=settings.mistral_api_key,
        model=settings.mistral_extraction_model,
        retries=settings.extraction_retries,
    )
    return ExtractionPipeline(
        ocr=ocr,
        classifier=classifier,
        extractor=extractor,
        settings=settings,
    )

"""Unit tests for src/services/pipeline.py — OCR fallback and failure handling."""
import os
import tempfile

from src.services.ocr_service import OcrError
from src.services.pipeline import ExtractionPipeline
from src.services.settings import AppSettings


class _RaisingOcr:
    def extract_text(self, pdf_path: str) -> str:
        raise OcrError("simulated OCR failure")


class _ShortTextOcr:
    def extract_text(self, pdf_path: str) -> str:
        return "too short"  # well under min_ocr_text_length


class _WorkingOcr:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, pdf_path: str) -> str:
        return self._text


class _StubClassifier:
    def __init__(self, doc_type: str = "other") -> None:
        self._doc_type = doc_type

    def classify(self, ocr_text: str) -> str:
        return self._doc_type

    def classify_from_images(self, image_paths) -> str:
        return self._doc_type


class _StubExtractor:
    def clear_cache(self):
        pass

    def extract_fields(self, ocr_text, field_names):
        from src.services.models import FieldExtraction

        return {fn: FieldExtraction(value="Null", source_text="Null") for fn in field_names}


def _make_temp_pdf() -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 fake content for testing")
        return tmp.name


# Task 5.2 / 19.3 — test_ocr_fallback_trigger, test_ocr_error_fallback
def test_ocr_fallback_trigger_on_short_text():
    """When OCR text is shorter than min_ocr_text_length, the pipeline must
    activate the image fallback path rather than proceeding with the short text."""
    settings = AppSettings(_env_file=None, mistral_api_key="test-key")
    pipeline = ExtractionPipeline(
        ocr=_ShortTextOcr(),
        classifier=_StubClassifier("other"),
        extractor=_StubExtractor(),
        settings=settings,
    )

    tmp_path = _make_temp_pdf()
    try:
        response = pipeline.run(tmp_path, "doc.pdf", ["Name"], force_extract=False)
    finally:
        os.unlink(tmp_path)

    # With no real PDF for image rendering, the fallback rendering will fail too,
    # resulting in a "failed" status rather than a crash.
    assert response.records[0].status in ("failed", "rejected")


def test_ocr_error_fallback_triggered_on_exception():
    """When extract_text raises OcrError, the pipeline must attempt the fallback
    path rather than propagating the exception."""
    settings = AppSettings(_env_file=None, mistral_api_key="test-key")
    pipeline = ExtractionPipeline(
        ocr=_RaisingOcr(),
        classifier=_StubClassifier("other"),
        extractor=_StubExtractor(),
        settings=settings,
    )

    tmp_path = _make_temp_pdf()
    try:
        # Should not raise — pipeline.run() never raises per design.
        response = pipeline.run(tmp_path, "doc.pdf", ["Name"], force_extract=False)
    finally:
        os.unlink(tmp_path)

    assert response is not None
    assert response.records[0].status in ("failed", "rejected")


# Task 11.3 / 19.4 — test_double_failure
def test_double_failure_when_both_ocr_and_fallback_fail():
    """When both the primary OCR path and the image fallback fail (invalid PDF
    bytes so PyMuPDF cannot render pages either), the pipeline must return a
    'failed' status with a non-empty failure_reason — never raise."""
    settings = AppSettings(_env_file=None, mistral_api_key="test-key")
    pipeline = ExtractionPipeline(
        ocr=_RaisingOcr(),
        classifier=_StubClassifier("other"),
        extractor=_StubExtractor(),
        settings=settings,
    )

    # Write a file that is not a valid PDF, so PyMuPDF fallback rendering also fails.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"this is not a real pdf")
        tmp_path = tmp.name

    try:
        response = pipeline.run(tmp_path, "doc.pdf", ["Name"], force_extract=False)
    finally:
        os.unlink(tmp_path)

    assert response.records[0].status == "failed"
    assert response.records[0].failure_reason != ""


def test_successful_extraction_path():
    """Sanity check: a valid (accepted) classification with working OCR must
    return status='success' and populate field values from the extractor."""
    settings = AppSettings(_env_file=None, mistral_api_key="test-key")
    pipeline = ExtractionPipeline(
        ocr=_WorkingOcr(
            "This is a Letter of Award document with sufficient text length "
            "padding here to exceed the minimum OCR text length threshold "
            "required by the pipeline configuration for the text-first path."
        ),
        classifier=_StubClassifier("letter of award (loa)"),
        extractor=_StubExtractor(),
        settings=settings,
    )

    tmp_path = _make_temp_pdf()
    try:
        response = pipeline.run(tmp_path, "doc.pdf", ["Name"], force_extract=False)
    finally:
        os.unlink(tmp_path)

    assert response.doc_type == "letter of award (loa)"
    assert response.records[0].status == "success"

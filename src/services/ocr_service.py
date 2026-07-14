"""Mistral OCR service for converting PDFs to structured markdown text.

Uses a single base64 data URI call (no file upload / signed-URL step)
to minimise latency (one API round trip instead of three).
"""
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OcrError(Exception):
    """Raised when Mistral OCR fails and the caller should activate the fallback."""


class MistralOcrClient:
    """Converts a PDF to structured markdown text via Mistral OCR.

    The PDF is encoded as a base64 data URI and sent in a single OCR call.
    This is faster and simpler than the upload → signed-URL → OCR pattern.
    """

    def __init__(self, api_key: str, model: str = "mistral-ocr-latest") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None  # lazily initialised

    def _get_client(self):
        if self._client is None:
            try:
                from mistralai.client.sdk import Mistral
            except ImportError:
                from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key)
        return self._client

    def extract_text(self, pdf_path: str) -> str:
        """Convert the PDF at *pdf_path* to structured markdown text.

        Returns:
            Concatenated markdown text for all pages (joined by double newline).

        Raises:
            OcrError: on any API failure, timeout, or unexpected error.
        """
        try:
            client = self._get_client()

            pdf_bytes = Path(pdf_path).read_bytes()
            data_uri = (
                "data:application/pdf;base64,"
                + base64.b64encode(pdf_bytes).decode("ascii")
            )

            response = client.ocr.process(
                model=self.model,
                document={"type": "document_url", "document_url": data_uri},
            )

            pages = response.pages or []
            text_parts = [page.markdown for page in pages if page.markdown]
            structured_text = "\n\n".join(text_parts)

            logger.debug(
                "Mistral OCR complete: %d pages, %d characters",
                len(pages),
                len(structured_text),
            )

            return structured_text

        except Exception as exc:
            logger.warning("Mistral OCR failed: %s: %s", type(exc).__name__, exc)
            raise OcrError(f"OCR failed: {type(exc).__name__}: {exc}") from exc

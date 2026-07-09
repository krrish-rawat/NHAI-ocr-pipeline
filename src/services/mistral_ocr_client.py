import base64
import logging
from pathlib import Path

from src.services.mistral_common import (
    API_TIMEOUT_SECONDS,
    MIN_TEXT_LENGTH,
    import_mistral,
)

logger = logging.getLogger(__name__)


class MistralOcrClient:
    """Calls the Mistral OCR API to convert a PDF into structured markdown text."""

    def __init__(self, api_key: str, model: str = "mistral-ocr-latest") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None  # lazily created and reused across calls

    def _get_client(self):
        """Return a cached Mistral client, creating it once on first use."""
        if self._client is None:
            Mistral = import_mistral()
            self._client = Mistral(
                api_key=self.api_key,
                timeout_ms=API_TIMEOUT_SECONDS * 1000,
            )
        return self._client

    def extract_text(self, pdf_path: str) -> str:
        """Convert PDF at pdf_path to structured markdown text via Mistral OCR.

        The PDF is sent inline as a base64 data URI in a single OCR API call —
        this avoids the separate upload + get_signed_url round trips that the
        Files API flow requires, cutting OCR latency roughly in half for
        typical documents (2 network calls saved).

        Returns:
            Concatenated structured text for all pages, joined by newlines.

        Raises:
            ImportError: If the mistralai package is not installed.
            TimeoutError: If the API call exceeds the configured timeout.
            Exception: On network/auth/API errors (non-ImportError).
        """
        client = self._get_client()

        pdf_file = Path(pdf_path)
        with open(pdf_file, "rb") as f:
            pdf_bytes = f.read()

        data_uri = "data:application/pdf;base64," + base64.b64encode(pdf_bytes).decode("ascii")

        response = client.ocr.process(
            model=self.model,
            document={
                "type": "document_url",
                "document_url": data_uri,
                "document_name": pdf_file.name,
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

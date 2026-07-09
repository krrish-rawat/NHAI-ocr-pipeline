import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 50  # Characters; below this threshold text is considered unusable
_API_TIMEOUT = 8       # Seconds


class MistralOcrClient:
    """Calls the Mistral OCR API to convert a PDF into structured markdown text."""

    def __init__(self, api_key: str, model: str = "mistral-ocr-latest") -> None:
        self.api_key = api_key
        self.model = model

    def extract_text(self, pdf_path: str) -> str:
        """Convert PDF at pdf_path to structured markdown text via Mistral OCR.

        Returns:
            Concatenated structured text for all pages, joined by newlines.

        Raises:
            ImportError: If the mistralai package is not installed.
            TimeoutError: If the API call exceeds 8 seconds.
            Exception: On network/auth/API errors (non-ImportError).
        """
        try:
            from mistralai.client.sdk import Mistral
        except ImportError:
            try:
                from mistralai import Mistral
            except ImportError:
                raise ImportError(
                    "The 'mistralai' package is required for Mistral OCR. "
                    "Install it with: pip install mistralai"
                )

        client = Mistral(api_key=self.api_key, timeout_ms=_API_TIMEOUT * 1000)

        # Upload PDF file to Mistral
        pdf_file = Path(pdf_path)
        with open(pdf_file, "rb") as f:
            uploaded = client.files.upload(
                file={"file_name": pdf_file.name, "content": f},
                purpose="ocr",
            )

        # Get signed URL for the uploaded file
        signed_url = client.files.get_signed_url(file_id=uploaded.id)

        # Call OCR endpoint
        response = client.ocr.process(
            model=self.model,
            document={
                "type": "document_url",
                "document_url": signed_url.url,
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

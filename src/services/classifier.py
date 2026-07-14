"""Phase 1 document classifier using mistral-small-latest.

Classifies OCR text (fast text path) or rendered images (fallback path)
into one of the five accepted NHAI document types or "other".
"""
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ACCEPTED_TYPES = frozenset([
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
    "debarment records",
])

_CLASSIFICATION_SYSTEM_PROMPT = """\
You are a document classifier for official NHAI (National Highways Authority of India) documents.
Your ONLY task is to classify the document type.

Choose EXACTLY ONE from this list:
- "letter of award (loa)" — a contract award letter
- "completion certificate (cc)" — a completion certificate (not provisional)
- "provisional completion certificate (pcc)" — a provisional completion certificate
- "financial closure" — a financial closure document
- "debarment records" — a debarment, blacklisting, or restriction-from-participation document
- "other" — any other document type

Return ONLY the classification string, nothing else. No explanation, no JSON, just the type string.

Examples:
- "Letter of Award" or "LOA" in the text → "letter of award (loa)"
- "Completion Certificate" with "Provisional" → "provisional completion certificate (pcc)"
- "Completion Certificate" without "Provisional" → "completion certificate (cc)"
- "Financial Closure" → "financial closure"
- "Restriction for Participation", "Debarment", "Blacklisted", "not allowed to participate" → "debarment records"
- Invoice, purchase order, or other → "other"
"""


def _normalize_doc_type(raw: str) -> str:
    """Normalize the model's response to one of the expected type strings."""
    normalized = raw.strip().lower()
    if normalized in ACCEPTED_TYPES:
        return normalized
    # Fuzzy fallback for common partial responses
    if "provisional" in normalized:
        return "provisional completion certificate (pcc)"
    if "completion" in normalized and "certificate" in normalized:
        return "completion certificate (cc)"
    if "letter" in normalized or "loa" in normalized or "award" in normalized:
        return "letter of award (loa)"
    if "financial" in normalized or "closure" in normalized:
        return "financial closure"
    if "debarment" in normalized or "blacklist" in normalized or "restriction" in normalized:
        return "debarment records"
    return "other"


class MistralClassifier:
    """Phase 1 classifier using mistral-small-latest."""

    def __init__(self, api_key: str, model: str = "mistral-small-latest") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from mistralai.client.sdk import Mistral
            except ImportError:
                from mistralai import Mistral
            self._client = Mistral(api_key=self.api_key)
        return self._client

    def classify(self, ocr_text: str) -> str:
        """Classify a document from its OCR text.

        Returns one of the six type strings (lower-case).
        Falls back to "other" on any API error.
        """
        try:
            client = self._get_client()
            response = client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": _CLASSIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Document text:\n\n{ocr_text}"},
                ],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or "other"
            doc_type = _normalize_doc_type(raw)
            logger.debug("Classifier returned: %r → %r", raw, doc_type)
            return doc_type
        except Exception as exc:
            logger.warning("Classification failed: %s: %s", type(exc).__name__, exc)
            return "other"

    def classify_from_images(self, image_paths: list[str]) -> str:
        """Classify a document from rendered page images (fallback path).

        Images are base64-encoded and sent as vision content.
        Falls back to "other" on any API error.
        """
        try:
            client = self._get_client()

            image_content = []
            for img_path in image_paths[:3]:  # cap at 3 pages for classification
                img_bytes = Path(img_path).read_bytes()
                b64 = base64.b64encode(img_bytes).decode("ascii")
                image_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

            image_content.append({
                "type": "text",
                "text": "What type of NHAI document is this? " + _CLASSIFICATION_SYSTEM_PROMPT,
            })

            response = client.chat.complete(
                model=self.model,
                messages=[{"role": "user", "content": image_content}],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or "other"
            doc_type = _normalize_doc_type(raw)
            logger.debug("Image classifier returned: %r → %r", raw, doc_type)
            return doc_type
        except Exception as exc:
            logger.warning("Image classification failed: %s: %s", type(exc).__name__, exc)
            return "other"

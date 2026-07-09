"""Shared helpers for Mistral SDK clients (OCR + LLM).

Centralizes the version-specific import path and shared constants so there is
a single place to update if the mistralai SDK layout changes again.
"""

# Minimum characters below which OCR output is treated as unusable and the
# pipeline falls back to the image-based path.
MIN_TEXT_LENGTH = 50

# Default timeout (seconds) for Mistral API calls.
API_TIMEOUT_SECONDS = 8


def import_mistral():
    """Import and return the Mistral SDK class.

    Handles both the newer namespaced path (mistralai.client.sdk) and the
    top-level export, raising a clear ImportError with install instructions
    if the package is missing.
    """
    try:
        from mistralai.client.sdk import Mistral
        return Mistral
    except ImportError:
        pass
    try:
        from mistralai import Mistral
        return Mistral
    except ImportError:
        raise ImportError(
            "The 'mistralai' package is required for Mistral features. "
            "Install it with: pip install mistralai"
        )

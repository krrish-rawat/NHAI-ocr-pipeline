"""Application settings for the NHAI PDF Data Extraction rebuild.

All configuration is read from environment variables (or .env file).
The app fails fast at startup if MISTRAL_API_KEY is absent.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    # Required — app fails to start without this
    mistral_api_key: str = ""

    # Mistral model names with documented defaults
    mistral_ocr_model: str = "mistral-ocr-latest"
    mistral_classification_model: str = "mistral-small-latest"
    mistral_extraction_model: str = "mistral-large-latest"

    # Upload limits
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB

    # OCR quality threshold — text shorter than this triggers fallback
    min_ocr_text_length: int = 100

    # Number of LLM call retries on validation failure (0 = no retry)
    extraction_retries: int = 1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("mistral_api_key", mode="before")
    @classmethod
    def key_must_be_present(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError(
                "MISTRAL_API_KEY is required. "
                "Set it as an environment variable or add it to .env"
            )
        return str(v).strip()


# Module-level singleton — importing this triggers startup validation
settings = AppSettings()

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AppSettings:
    model_name: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    extraction_retries: int = int(os.getenv("EXTRACTION_RETRIES", "2"))
    summary_timeout_seconds: int = int(os.getenv("SUMMARY_TIMEOUT_SECONDS", "60"))

    # Mistral OCR configuration
    mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
    mistral_ocr_model: str = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
    mistral_llm_model: str = os.getenv("MISTRAL_LLM_MODEL", "mistral-small-latest")
    mistral_extraction_model: str = os.getenv("MISTRAL_EXTRACTION_MODEL", "mistral-large-latest")
    use_mistral_ocr: bool = bool(os.getenv("USE_MISTRAL_OCR", "") or os.getenv("MISTRAL_API_KEY"))
    use_mistral_llm: bool = bool(os.getenv("USE_MISTRAL_LLM", "") or os.getenv("MISTRAL_API_KEY"))


settings = AppSettings()

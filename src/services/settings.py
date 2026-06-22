import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AppSettings:
    model_name: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
    extraction_retries: int = int(os.getenv("EXTRACTION_RETRIES", "3"))


settings = AppSettings()

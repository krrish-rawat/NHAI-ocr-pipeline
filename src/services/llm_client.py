import json
import time
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from PIL import Image
from pydantic import BaseModel, Field, create_model

from src.services.settings import settings


def build_response_schema(attributes: list[str]) -> type[BaseModel]:
    """
    Dynamically build a Pydantic model matching the user's requested attributes
    plus per-field source citations.
    """
    class SourceCitation(BaseModel):
        pageNumber: int = Field(description="1-based PDF page number where the value appears.")
        text: str = Field(description="Short exact source snippet from the PDF for this value.")
        confidence: str = Field(description="Extraction confidence: high, medium, low, or unknown.")

    source_fields: dict[str, Any] = {
        attr: (
            SourceCitation,
            Field(description=f"Source citation for {attr}. Use pageNumber 0, text 'Null', and confidence 'unknown' if not found."),
        )
        for attr in attributes
    }
    SourceMetaModel = create_model("ExtractionSourceMeta", **source_fields)

    record_fields: dict[str, Any] = {
        attr: (str, Field(description=f"Extracted value for {attr}. Use 'Null' if not found."))
        for attr in attributes
    }
    record_fields["source_meta"] = (
        SourceMetaModel,
        Field(description="Per-field source citations keyed by requested attribute name."),
    )
    RecordModel = create_model("ExtractionRecord", **record_fields)

    class ExtractionResponse(BaseModel):
        records: list[RecordModel] = Field(  # type: ignore[valid-type]
            description="One object per person/entity found in the document."
        )

    return ExtractionResponse


class GeminiExtractionClient:
    """Gemini adapter isolated from API and orchestration code."""

    def __init__(self, model_name: str = settings.model_name, api_key: str | None = settings.gemini_api_key) -> None:
        self.model_name = model_name
        self.api_key = api_key
        genai.configure(api_key=api_key)

    def generate_json(
        self,
        prompt: str,
        images: list[Image.Image],
        retries: int = settings.extraction_retries,
        response_schema: type | None = None,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured.")

        model = genai.GenerativeModel(self.model_name)
        generation_config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        }
        if response_schema is not None:
            generation_config["response_schema"] = response_schema

        for attempt in range(retries):
            try:
                response = model.generate_content(
                    [prompt, *images],
                    generation_config=GenerationConfig(**generation_config),
                )
                return json.loads(response.text)
            except Exception as exc:
                if attempt == retries - 1:
                    raise ValueError(f"{type(exc).__name__}: {exc}") from exc

                # Short sleep before retry — keeps total retry overhead low
                time.sleep(1)

        return {}

    def generate_text(
        self,
        prompt: str,
        images: list[Image.Image],
        retries: int = settings.extraction_retries,
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is not configured.")

        model = genai.GenerativeModel(self.model_name)

        for attempt in range(retries):
            try:
                response = model.generate_content(
                    [prompt, *images],
                    generation_config=GenerationConfig(
                        temperature=0.0,
                    ),
                )
                return (response.text or "").strip()
            except Exception as exc:
                if attempt == retries - 1:
                    raise ValueError(f"{type(exc).__name__}: {exc}") from exc

                time.sleep(1)

        return ""

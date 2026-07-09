"""Mistral Chat LLM client — drop-in replacement for GeminiExtractionClient.

Uses Mistral's chat completion API for both classification (generate_text)
and structured extraction (generate_json with JSON mode).
"""

import json
import logging
import time
from typing import Any

from src.services.settings import settings

logger = logging.getLogger(__name__)


class MistralLLMClient:
    """Mistral chat adapter matching the GeminiExtractionClient interface."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "mistral-small-latest",
        extraction_model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.mistral_api_key
        self.model = model
        self.extraction_model = extraction_model or model

    def _get_client(self):
        """Lazy-import and instantiate Mistral client."""
        try:
            from mistralai.client.sdk import Mistral
        except ImportError:
            try:
                from mistralai import Mistral
            except ImportError:
                raise ImportError(
                    "The 'mistralai' package is required. "
                    "Install it with: pip install mistralai"
                )
        return Mistral(api_key=self.api_key)

    def generate_json(
        self,
        prompt: str,
        images: list | None = None,
        retries: int = settings.extraction_retries,
        response_schema: type | None = None,
        text_context: str | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON output from Mistral chat completion.

        Uses JSON response format to ensure valid JSON output.
        """
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not configured.")

        client = self._get_client()

        # Build the user message
        if text_context:
            user_content = text_context + "\n\n" + prompt
        else:
            # Fallback: just send the prompt (no image support in this client)
            user_content = prompt

        messages = [
            {
                "role": "system",
                "content": "You are a precise data extraction assistant. Always respond with valid JSON only. No markdown, no explanations, no code fences.",
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        for attempt in range(retries):
            try:
                response = client.chat.complete(
                    model=self.extraction_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )

                raw_text = response.choices[0].message.content.strip()

                # Strip markdown code fences if present
                if raw_text.startswith("```"):
                    lines = raw_text.split("\n")
                    # Remove first line (```json) and last line (```)
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw_text = "\n".join(lines)

                return json.loads(raw_text)

            except json.JSONDecodeError as exc:
                logger.warning(
                    "Mistral JSON parse failed (attempt %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt == retries - 1:
                    raise ValueError(f"Mistral returned invalid JSON: {exc}") from exc
                time.sleep(1)

            except Exception as exc:
                logger.warning(
                    "Mistral generate_json failed (attempt %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt == retries - 1:
                    raise ValueError(f"{type(exc).__name__}: {exc}") from exc
                time.sleep(1)

        return {}

    def generate_text(
        self,
        prompt: str,
        images: list | None = None,
        retries: int = settings.extraction_retries,
        text_context: str | None = None,
    ) -> str:
        """Generate plain text response from Mistral chat completion."""
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not configured.")

        client = self._get_client()

        # Build the user message
        if text_context:
            user_content = text_context + "\n\n" + prompt
        else:
            user_content = prompt

        messages = [
            {
                "role": "system",
                "content": "You are a document classification assistant. Respond with only the classification string, nothing else.",
            },
            {
                "role": "user",
                "content": user_content,
            },
        ]

        for attempt in range(retries):
            try:
                response = client.chat.complete(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                )

                return (response.choices[0].message.content or "").strip()

            except Exception as exc:
                logger.warning(
                    "Mistral generate_text failed (attempt %d/%d): %s",
                    attempt + 1, retries, exc,
                )
                if attempt == retries - 1:
                    raise ValueError(f"{type(exc).__name__}: {exc}") from exc
                time.sleep(1)

        return ""

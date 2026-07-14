"""Shared mock helpers for property-based tests.

These mocks stub out the Mistral API layer so property tests run fast and
deterministically without live network calls.
"""
from __future__ import annotations

import re

from src.services.models import FieldExtraction
from src.services.utils import normalize_text


class MockChatResponse:
    """Mimics the shape of a Mistral chat.complete() response."""

    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class MockChatClient:
    """Stand-in for the `.chat` namespace of the Mistral SDK client."""

    def __init__(self, complete_fn) -> None:
        self._complete_fn = complete_fn

    def complete(self, **kwargs):
        return self._complete_fn(**kwargs)


class MockMistralSDKClient:
    """Stand-in for the full Mistral() client — only `.chat.complete` is used
    by MistralExtractor / MistralClassifier."""

    def __init__(self, complete_fn) -> None:
        self.chat = MockChatClient(complete_fn)


def make_extractor_with_mock(complete_fn, retries: int = 1):
    """Build a MistralExtractor with its internal client swapped for a mock."""
    from src.services.extractor import MistralExtractor

    extractor = MistralExtractor(api_key="test-key", model="mock-model", retries=retries)
    extractor._client = MockMistralSDKClient(complete_fn)
    return extractor


def json_response_returning_value_in_text(ocr_text: str, field_name: str) -> str:
    """Build a chat-completion JSON payload whose value is guaranteed to be
    a substring of ocr_text (simulates a well-behaved, grounded LLM).

    Uses json.dumps for the individual field values so special characters
    (backslashes, quotes) in generated test text never produce invalid JSON.
    """
    import json as _json

    tokens = [t for t in re.split(r"\s+", ocr_text.strip()) if t]
    value = tokens[0] if tokens else "Null"
    return _json.dumps({"value": value, "source_text": ocr_text[:60]})

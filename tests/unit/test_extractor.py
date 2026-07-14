"""Unit tests for src/services/extractor.py — MistralExtractor retry & temperature."""
import json

from tests.property.conftest import MockChatResponse, MockMistralSDKClient, make_extractor_with_mock


# Task 8.2 / 19.5 — test_pydantic_validation_retry
def test_pydantic_validation_retry_succeeds_on_second_attempt():
    calls = {"n": 0}

    def complete_fn(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return MockChatResponse("not valid json{{{")
        return MockChatResponse(json.dumps({"value": "ABC", "source_text": "text with ABC in it"}))

    extractor = make_extractor_with_mock(complete_fn, retries=1)
    result = extractor.extract_field("text with ABC in it", "Name")

    assert result.value == "ABC"
    assert calls["n"] == 2


def test_pydantic_validation_retry_falls_back_to_null_after_exhausting_retries():
    def complete_fn(**kwargs):
        return MockChatResponse("still not valid json{{{")

    extractor = make_extractor_with_mock(complete_fn, retries=1)
    result = extractor.extract_field("some ocr text", "Name")

    assert result.value == "Null"
    assert result.source_text == "Null"


# Task 8.3 / 19.6 — test_temperature_zero
def test_extractor_calls_with_temperature_zero():
    captured_kwargs = {}

    def complete_fn(**kwargs):
        captured_kwargs.update(kwargs)
        return MockChatResponse(json.dumps({"value": "Null", "source_text": "Null"}))

    extractor = make_extractor_with_mock(complete_fn, retries=0)
    extractor.extract_field("some text", "Field")

    assert captured_kwargs.get("temperature") == 0.0


def test_classifier_calls_with_temperature_zero():
    from src.services.classifier import MistralClassifier

    captured_kwargs = {}

    def complete_fn(**kwargs):
        captured_kwargs.update(kwargs)
        return MockChatResponse("other")

    classifier = MistralClassifier(api_key="test-key")
    classifier._client = MockMistralSDKClient(complete_fn)
    classifier.classify("some ocr text")

    assert captured_kwargs.get("temperature") == 0.0


def test_extract_field_cache_hit_does_not_call_llm_twice():
    calls = {"n": 0}

    def complete_fn(**kwargs):
        calls["n"] += 1
        return MockChatResponse(json.dumps({"value": "ABC", "source_text": "ABC is here"}))

    extractor = make_extractor_with_mock(complete_fn, retries=0)
    extractor.extract_field("ABC is here", "Name")
    extractor.extract_field("ABC is here", "Name")

    assert calls["n"] == 1


def test_clear_cache_empties_stored_results():
    def complete_fn(**kwargs):
        return MockChatResponse(json.dumps({"value": "ABC", "source_text": "ABC is here"}))

    extractor = make_extractor_with_mock(complete_fn, retries=0)
    extractor.extract_field("ABC is here", "Name")
    assert len(extractor._cache) == 1

    extractor.clear_cache()
    assert len(extractor._cache) == 0

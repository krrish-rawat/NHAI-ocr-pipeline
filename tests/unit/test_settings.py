"""Unit tests for src/services/settings.py — AppSettings startup validation."""
import pytest
from pydantic import ValidationError

from src.services.settings import AppSettings


# Task 19.8 — test_settings_missing_key
def test_settings_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, mistral_api_key="")


def test_settings_present_key_succeeds():
    settings = AppSettings(_env_file=None, mistral_api_key="sk-test-123")
    assert settings.mistral_api_key == "sk-test-123"


def test_settings_defaults():
    settings = AppSettings(_env_file=None, mistral_api_key="sk-test-123")
    assert settings.mistral_ocr_model == "mistral-ocr-latest"
    assert settings.mistral_classification_model == "mistral-small-latest"
    assert settings.mistral_extraction_model == "mistral-large-latest"
    assert settings.max_upload_bytes == 25 * 1024 * 1024
    assert settings.min_ocr_text_length == 100
    assert settings.extraction_retries == 1

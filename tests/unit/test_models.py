"""Unit tests for src/services/models.py — FieldExtraction.coerce_null validator."""
from src.services.models import FieldExtraction


# Task 2.2 — coerce_null validator tests
def test_coerce_null_from_none():
    fe = FieldExtraction(value=None, source_text=None)
    assert fe.value == "Null"
    assert fe.source_text == "Null"


def test_coerce_null_from_empty_string():
    fe = FieldExtraction(value="", source_text="")
    assert fe.value == "Null"
    assert fe.source_text == "Null"


def test_coerce_null_from_whitespace_only():
    fe = FieldExtraction(value="   ", source_text="\t\n")
    assert fe.value == "Null"
    assert fe.source_text == "Null"


def test_coerce_null_preserves_valid_string():
    fe = FieldExtraction(value="ABC Corp", source_text="The contractor is ABC Corp")
    assert fe.value == "ABC Corp"
    assert fe.source_text == "The contractor is ABC Corp"


def test_coerce_null_strips_surrounding_whitespace():
    fe = FieldExtraction(value="  ABC Corp  ", source_text="  text  ")
    assert fe.value == "ABC Corp"
    assert fe.source_text == "text"

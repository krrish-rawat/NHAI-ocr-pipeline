"""Unit tests for src/services/utils.py — field normalization and grounding."""
from src.services.utils import deduplicate_fields, score_grounding


# Task 19.1 — test_normalize_fields
def test_normalize_fields_preserves_first_occurrence_order():
    result = deduplicate_fields(["Name", "Date of Birth", "PAN"])
    assert result == ["Name", "Date of Birth", "PAN"]


def test_normalize_fields_dedupes_case_insensitive():
    result = deduplicate_fields(["Name", "name", "NAME"])
    assert result == ["Name"]  # first occurrence casing preserved


def test_normalize_fields_strips_whitespace():
    result = deduplicate_fields(["  Name  ", "PAN "])
    assert result == ["Name", "PAN"]


def test_normalize_fields_handles_empty_input():
    assert deduplicate_fields([]) == []


def test_normalize_fields_skips_blank_entries():
    result = deduplicate_fields(["Name", "   ", "", "PAN"])
    assert result == ["Name", "PAN"]


# Task 19.2 — test_grounding_check (all four confidence levels)
def test_grounding_check_high_confidence():
    assert score_grounding("ABC Corp", "The contractor is ABC Corp based in Delhi") == "high"


def test_grounding_check_medium_confidence():
    # tokens present but not contiguous
    assert score_grounding("ABC Corp", "ABC is located near the Corp office") == "medium"


def test_grounding_check_low_confidence():
    assert score_grounding("XYZ Ltd", "The contractor is ABC Corp based in Delhi") == "low"


def test_grounding_check_unknown_for_null():
    assert score_grounding("Null", "anything here") == "unknown"

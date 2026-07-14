"""Shared utility functions for field normalization, hashing, and grounding.

These utilities are pure functions (no side effects) and are imported by
multiple service modules.
"""
import hashlib
import re

from src.services.models import GroundingConfidence


def normalize_field_name(field_name: str) -> str:
    """Strip, collapse whitespace, and lowercase a field name for cache keying."""
    return re.sub(r"\s+", " ", field_name.strip()).lower()


def normalize_text(text: str) -> str:
    """Collapse whitespace and lowercase text for grounding comparisons."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def ocr_hash(ocr_text: str) -> str:
    """Return the SHA-256 hex digest of the OCR text string."""
    return hashlib.sha256(ocr_text.encode("utf-8")).hexdigest()


def cache_key(ocr_text: str, field_name: str) -> tuple[str, str]:
    """Return the stability-cache key for a (document, field) pair."""
    return (ocr_hash(ocr_text), normalize_field_name(field_name))


def deduplicate_fields(fields: list[str]) -> list[str]:
    """Deduplicate field names preserving first-occurrence order.

    Deduplication is case-insensitive and whitespace-insensitive:
    "  Name  " and "name" are considered the same field.
    The first-occurrence casing is preserved in the output.
    """
    seen: set[str] = set()
    result: list[str] = []
    for field in fields:
        normalized = normalize_field_name(field)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(field.strip())
    return result


def score_grounding(value: str, source_text: str) -> GroundingConfidence:
    """Compute grounding confidence by comparing value against source_text.

    Returns:
        "high"    — normalized value is a contiguous substring of normalized source_text
        "medium"  — every token of normalized value appears in normalized source_text
                    but not contiguously
        "low"     — one or more tokens of a non-Null value are absent from source_text
        "unknown" — value is "Null"
    """
    v_norm = normalize_text(value)
    s_norm = normalize_text(source_text)

    if v_norm in ("null", ""):
        return "unknown"

    if v_norm in s_norm:
        return "high"

    tokens = [t for t in v_norm.split() if len(t) >= 2]
    if tokens and all(t in s_norm for t in tokens):
        return "medium"

    return "low"

"""Property-based tests for the NHAI extraction rebuild.

Each test corresponds to a correctness property defined in design.md.
Uses Hypothesis for universally-quantified statement verification.
"""
from __future__ import annotations

import csv
import io
import json

from hypothesis import given, settings as hyp_settings, HealthCheck
from hypothesis import strategies as st

from src.services.extractor import MistralExtractor
from src.services.classifier import ACCEPTED_TYPES
from src.services.models import (
    ExtractionRecord,
    ExtractionResponse,
    FieldResult,
    SourceMeta,
)
from src.services.serializers import records_to_csv, records_to_json
from src.services.utils import normalize_text

from tests.property.conftest import (
    MockMistralSDKClient,
    json_response_returning_value_in_text,
    make_extractor_with_mock,
)

# Common settings: suppress the "function-scoped fixture" health check since
# these tests build fresh mock objects per Hypothesis example (not via fixtures).
_COMMON_SETTINGS = hyp_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)

_SAFE_TEXT = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),  # printable ASCII
    min_size=1,
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: nhai-extraction-rebuild, Property 1: Output Stability
# Validates: Requirements R5.1, R5.2, R5.3, R5.4, R5.5
# ─────────────────────────────────────────────────────────────────────────────
@given(
    ocr_text=_SAFE_TEXT.filter(lambda s: len(s.strip()) >= 5),
    field_name=_SAFE_TEXT.filter(lambda s: s.strip()),
    other_field_name=_SAFE_TEXT.filter(lambda s: s.strip()),
)
@_COMMON_SETTINGS
def test_output_stability(ocr_text, field_name, other_field_name):
    """Extracting the same field twice (with or without an unrelated field
    extracted in between) must return a character-for-character identical
    FieldExtraction — this is the structural stability guarantee."""

    call_count = {"n": 0}

    def complete_fn(**kwargs):
        call_count["n"] += 1
        from tests.property.conftest import MockChatResponse

        return MockChatResponse(json_response_returning_value_in_text(ocr_text, field_name))

    extractor = make_extractor_with_mock(complete_fn)

    result_1 = extractor.extract_field(ocr_text, field_name)
    result_2 = extractor.extract_field(ocr_text, field_name)  # cache hit expected
    assert result_1 == result_2

    calls_after_two_same_field = call_count["n"]
    assert calls_after_two_same_field == 1, "second call for the same field must be a cache hit"

    # Extract an unrelated field in between; the first field's cached result
    # must remain unchanged.
    if other_field_name.strip().lower() != field_name.strip().lower():
        extractor.extract_field(ocr_text, other_field_name)

    result_3 = extractor.extract_field(ocr_text, field_name)
    assert result_1 == result_3


# ─────────────────────────────────────────────────────────────────────────────
# Feature: nhai-extraction-rebuild, Property 2: Verbatim Grounding
# Validates: Requirements R4.2, R4.6
# ─────────────────────────────────────────────────────────────────────────────
@given(
    ocr_text=_SAFE_TEXT.filter(lambda s: len(s.strip()) >= 5),
    field_name=_SAFE_TEXT.filter(lambda s: s.strip()),
    arbitrary_value=_SAFE_TEXT,
)
@_COMMON_SETTINGS
def test_verbatim_grounding(ocr_text, field_name, arbitrary_value):
    """If the LLM returns a value NOT present in the OCR text, the extractor's
    post-validation grounding check must overwrite it with Null — the
    extractor must never surface a hallucinated (non-grounded) value."""

    def complete_fn(**kwargs):
        from tests.property.conftest import MockChatResponse

        # Simulate a misbehaving LLM that may return an arbitrary value,
        # not necessarily present in ocr_text. json.dumps handles all escaping.
        payload = json.dumps({"value": arbitrary_value, "source_text": "irrelevant"})
        return MockChatResponse(payload)

    extractor = make_extractor_with_mock(complete_fn)
    result = extractor.extract_field(ocr_text, field_name)

    if result.value != "Null":
        assert normalize_text(result.value) in normalize_text(ocr_text), (
            f"Non-Null value {result.value!r} must appear in OCR text after grounding check"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Feature: nhai-extraction-rebuild, Property 3: Output Schema Stability
# Validates: Requirements R7.1, R7.2, R7.3, R7.4, R7.6
# ─────────────────────────────────────────────────────────────────────────────
_FIELD_NAME_STRATEGY = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),  # a-z only, avoids dup collisions
    min_size=1,
    max_size=15,
)


@given(
    field_names=st.lists(_FIELD_NAME_STRATEGY, min_size=1, max_size=6, unique=True),
    doc_type=st.sampled_from(list(ACCEPTED_TYPES) + ["other"]),
    source_file=st.text(min_size=1, max_size=20).filter(lambda s: s.strip()),
)
@_COMMON_SETTINGS
def test_output_schema_stability(field_names, doc_type, source_file):
    """The JSON output must always contain doc_type/field_names/records with
    every requested field present in every record; the CSV output columns
    must be exactly [source_file, *field_names, status, failure_reason]."""

    fields = {
        fn: FieldResult(value="some-value", source_meta=SourceMeta(text="src", confidence="high"))
        for fn in field_names
    }
    record = ExtractionRecord(source_file=source_file, fields=fields, status="success", failure_reason="")
    response = ExtractionResponse(doc_type=doc_type, field_names=field_names, records=[record])

    # JSON schema checks
    json_str = records_to_json(response, field_names)
    payload = json.loads(json_str)
    assert "doc_type" in payload
    assert "field_names" in payload
    assert "records" in payload
    for rec in payload["records"]:
        for fn in field_names:
            assert fn in rec["fields"], f"field {fn!r} missing from serialized record"

    # CSV schema checks
    csv_str = records_to_csv(response, field_names)
    # Strip BOM before parsing
    csv_str_clean = csv_str.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(csv_str_clean))
    expected_headers = ["source_file", *field_names, "status", "failure_reason"]
    assert reader.fieldnames == expected_headers


@given(
    hindi_value=st.text(
        alphabet=st.characters(min_codepoint=0x0900, max_codepoint=0x097F),  # Devanagari block
        min_size=1,
        max_size=20,
    ),
)
@_COMMON_SETTINGS
def test_output_schema_unicode_roundtrip(hindi_value):
    """Hindi/Devanagari characters must survive JSON and CSV serialization
    without corruption (mojibake, escaping, or byte-level loss)."""
    field_names = ["Name"]
    fields = {
        "Name": FieldResult(value=hindi_value, source_meta=SourceMeta(text=hindi_value, confidence="high"))
    }
    record = ExtractionRecord(source_file="doc.pdf", fields=fields, status="success", failure_reason="")
    response = ExtractionResponse(doc_type="debarment records", field_names=field_names, records=[record])

    json_str = records_to_json(response, field_names)
    payload = json.loads(json_str)
    assert payload["records"][0]["fields"]["Name"]["value"] == hindi_value

    csv_str = records_to_csv(response, field_names)
    csv_str_clean = csv_str.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(csv_str_clean))
    rows = list(reader)
    assert rows[0]["Name"] == hindi_value


# ─────────────────────────────────────────────────────────────────────────────
# Feature: nhai-extraction-rebuild, Property 4: Classification Gate
# Validates: Requirements R3.3, R3.4
# ─────────────────────────────────────────────────────────────────────────────
class _StubOcr:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, pdf_path: str) -> str:
        return self._text


class _StubClassifier:
    def __init__(self, doc_type: str) -> None:
        self._doc_type = doc_type

    def classify(self, ocr_text: str) -> str:
        return self._doc_type

    def classify_from_images(self, image_paths):
        return self._doc_type


class _StubExtractor:
    """Minimal stand-in with an extract_fields + clear_cache interface."""

    def clear_cache(self):
        pass

    def extract_fields(self, ocr_text, field_names):
        from src.services.models import FieldExtraction

        return {fn: FieldExtraction(value="Null", source_text="Null") for fn in field_names}


@given(
    ocr_text=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=20, max_size=60),
    force_extract=st.booleans(),
    field_names=st.lists(_FIELD_NAME_STRATEGY, min_size=1, max_size=4, unique=True),
)
@_COMMON_SETTINGS
def test_classification_gate(ocr_text, force_extract, field_names):
    # Pad to exceed min_ocr_text_length so the pipeline exercises the text-first
    # path (Phase 1 gate) rather than falling back to the image path.
    ocr_text = ocr_text + " " * 120
    """When the classifier returns 'other' and force_extract is False, the
    pipeline must reject; when force_extract is True, it must proceed."""
    import tempfile
    import os

    from src.services.pipeline import ExtractionPipeline
    from src.services.settings import AppSettings

    settings = AppSettings(mistral_api_key="test-key")
    pipeline = ExtractionPipeline(
        ocr=_StubOcr(ocr_text),
        classifier=_StubClassifier("other"),
        extractor=_StubExtractor(),
        settings=settings,
    )

    # Pipeline.run() reads the file to check OCR path but our stub OCR ignores
    # pdf_path entirely, so any existing temp file path is fine.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 fake")
        tmp_path = tmp.name

    try:
        response = pipeline.run(tmp_path, "doc.pdf", field_names, force_extract=force_extract)
    finally:
        os.unlink(tmp_path)

    if not force_extract:
        for rec in response.records:
            assert rec.status == "rejected"
            assert rec.failure_reason != ""
    else:
        for rec in response.records:
            assert rec.status != "rejected"


# ─────────────────────────────────────────────────────────────────────────────
# Feature: nhai-extraction-rebuild, Property 5: OCR Single-Call Invariant
#          and Stability Cache Hit Rate
# Validates: Requirements R9.2, R9.3, R5.5
# ─────────────────────────────────────────────────────────────────────────────
class _CountingStubOcr:
    def __init__(self, text: str) -> None:
        self._text = text
        self.call_count = 0

    def extract_text(self, pdf_path: str) -> str:
        self.call_count += 1
        return self._text


@given(
    ocr_text=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=20, max_size=60),
    field_names=st.lists(_FIELD_NAME_STRATEGY, min_size=2, max_size=6, unique=True),
)
@_COMMON_SETTINGS
def test_ocr_single_call_and_cache(ocr_text, field_names):
    """OCR must be invoked exactly once per pipeline run regardless of how
    many fields are requested; duplicate (post-normalization) field names
    must hit the extractor cache rather than triggering a second LLM call."""
    import tempfile
    import os

    from src.services.pipeline import ExtractionPipeline
    from src.services.settings import AppSettings

    # Pad to exceed min_ocr_text_length so the pipeline stays on the text-first
    # path rather than falling back to image rendering.
    ocr_text = ocr_text + " " * 120

    call_counter = {"n": 0}

    def complete_fn(**kwargs):
        call_counter["n"] += 1
        from tests.property.conftest import MockChatResponse

        return MockChatResponse(json_response_returning_value_in_text(ocr_text, "field"))

    stub_ocr = _CountingStubOcr(ocr_text)
    extractor = make_extractor_with_mock(complete_fn)
    settings = AppSettings(mistral_api_key="test-key")

    pipeline = ExtractionPipeline(
        ocr=stub_ocr,
        classifier=_StubClassifier(next(iter(ACCEPTED_TYPES))),
        extractor=extractor,
        settings=settings,
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 fake")
        tmp_path = tmp.name

    try:
        # Add a duplicate of the first field (different case) to verify cache reuse.
        duplicated_fields = field_names + [field_names[0].upper()]
        pipeline.run(tmp_path, "doc.pdf", duplicated_fields, force_extract=False)
    finally:
        os.unlink(tmp_path)

    assert stub_ocr.call_count == 1, "OCR must be called exactly once per pipeline run"

    # Deduplication happens inside pipeline.run() via deduplicate_fields, so the
    # duplicate normalized field name should never trigger a second LLM call.
    unique_normalized_count = len(set(fn.strip().lower() for fn in duplicated_fields))
    assert call_counter["n"] == unique_normalized_count

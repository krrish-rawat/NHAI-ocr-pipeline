"""Unit tests for src/services/serializers.py — JSON/CSV output, Unicode safety."""
import csv
import io
import json

from src.services.models import ExtractionRecord, ExtractionResponse, FieldResult, SourceMeta
from src.services.serializers import records_to_csv, records_to_json


def _make_response(value: str, field_name: str = "Name") -> ExtractionResponse:
    fields = {field_name: FieldResult(value=value, source_meta=SourceMeta(text=value, confidence="high"))}
    record = ExtractionRecord(source_file="doc.pdf", fields=fields, status="success", failure_reason="")
    return ExtractionResponse(doc_type="debarment records", field_names=[field_name], records=[record])


# Task 10.2 / 19.9 — test_csv_unicode
def test_csv_preserves_hindi_characters():
    hindi_name = "श्री गोली वेंकटेशम"
    response = _make_response(hindi_name)

    csv_str = records_to_csv(response, ["Name"])
    csv_clean = csv_str.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(csv_clean))
    rows = list(reader)

    assert rows[0]["Name"] == hindi_name


def test_json_preserves_hindi_characters():
    hindi_name = "श्री गोली वेंकटेशम"
    response = _make_response(hindi_name)

    json_str = records_to_json(response, ["Name"])
    payload = json.loads(json_str)

    assert payload["records"][0]["fields"]["Name"]["value"] == hindi_name
    # ensure_ascii=False means the raw string should contain actual Devanagari,
    # not \uXXXX escapes
    assert hindi_name in json_str


def test_csv_column_order():
    response = _make_response("Test Value", field_name="PAN")
    csv_str = records_to_csv(response, ["PAN"])
    csv_clean = csv_str.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(csv_clean))
    assert reader.fieldnames == ["source_file", "PAN", "status", "failure_reason"]


def test_json_emits_null_for_missing_field():
    response = _make_response("value", field_name="Name")
    # Request a field that isn't in the record
    json_str = records_to_json(response, ["Name", "PAN"])
    payload = json.loads(json_str)
    assert payload["records"][0]["fields"]["PAN"]["value"] == "Null"

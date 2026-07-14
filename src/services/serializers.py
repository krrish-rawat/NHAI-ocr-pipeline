"""Serializers for extraction output.

Pure functions: no I/O, no side effects. Accept Pydantic models, return strings.
Unicode (Hindi/Devanagari characters) is preserved without corruption in both formats.
"""
import csv
import io
import json

from src.services.models import ExtractionRecord, ExtractionResponse


def records_to_json(response: ExtractionResponse, field_names: list[str]) -> str:
    """Serialize an ExtractionResponse to a JSON string.

    Output shape:
        {
            "doc_type": str,
            "field_names": [str, ...],
            "records": [
                {
                    "source_file": str,
                    "fields": {
                        "<field_name>": {
                            "value": str,
                            "source_meta": {"text": str, "confidence": str}
                        }
                    },
                    "status": str,
                    "failure_reason": str
                }
            ]
        }

    Every requested field_name appears in every record (emitting "Null" if absent).
    Hindi and other Unicode characters are preserved (ensure_ascii=False).
    """
    records_out = []
    for record in response.records:
        fields_out = {}
        for fn in field_names:
            field_result = record.fields.get(fn)
            if field_result is None:
                fields_out[fn] = {
                    "value": "Null",
                    "source_meta": {"text": "Null", "confidence": "unknown"},
                }
            else:
                fields_out[fn] = {
                    "value": field_result.value,
                    "source_meta": {
                        "text": field_result.source_meta.text,
                        "confidence": field_result.source_meta.confidence,
                    },
                }

        records_out.append({
            "source_file": record.source_file,
            "fields": fields_out,
            "status": record.status,
            "failure_reason": record.failure_reason,
        })

    payload = {
        "doc_type": response.doc_type,
        "field_names": field_names,
        "records": records_out,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def records_to_csv(response: ExtractionResponse, field_names: list[str]) -> str:
    """Serialize an ExtractionResponse to a CSV string.

    Column order: source_file, <field_names in order>, status, failure_reason.
    Every requested field_name appears as a column (emitting "Null" if absent).
    Uses utf-8-sig (BOM) so Excel opens the file correctly without mojibake.
    """
    fieldnames = ["source_file", *field_names, "status", "failure_reason"]
    buffer = io.StringIO()
    # utf-8-sig adds a BOM that tells Excel the file is UTF-8
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()

    for record in response.records:
        row: dict[str, str] = {
            "source_file": record.source_file,
            "status": record.status,
            "failure_reason": record.failure_reason,
        }
        for fn in field_names:
            field_result = record.fields.get(fn)
            row[fn] = field_result.value if field_result else "Null"
        writer.writerow(row)

    # Prepend BOM for Excel compatibility
    return "\ufeff" + buffer.getvalue()

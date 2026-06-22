import csv
import io
import json


def records_to_csv(records: list[dict[str, str]], attributes: list[str]) -> str:
    fieldnames = ["source_file", *attributes, "status", "failure_reason"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for record in records:
        row = {fieldname: record.get(fieldname, "") for fieldname in fieldnames}
        writer.writerow(row)

    return buffer.getvalue()


def records_to_json_payload(records: list[dict[str, str]], attributes: list[str]) -> str:
    return json.dumps(
        {
            "attributes": attributes,
            "records": records,
        },
        indent=2,
        ensure_ascii=False,
    )

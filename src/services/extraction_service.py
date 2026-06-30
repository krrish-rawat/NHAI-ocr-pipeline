import re
from dataclasses import dataclass
from typing import Any

from src.services.llm_client import GeminiExtractionClient, build_response_schema
from src.services.pdf_renderer import PdfRenderer


def normalize_attributes(raw_attributes: str | list[str]) -> list[str]:
    if isinstance(raw_attributes, str):
        parts = re.split(r"[\n,]+", raw_attributes)
    else:
        parts = raw_attributes

    attributes: list[str] = []
    seen: set[str] = set()

    for part in parts:
        cleaned = re.sub(r"\s+", " ", str(part).strip())
        if not cleaned:
            continue

        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            attributes.append(cleaned)

    return attributes


def build_dynamic_prompt(attributes: list[str]) -> str:
    fields = "\n".join(f"- {attribute}" for attribute in attributes)

    return f"""
You are an expert data extractor for official PDF documents.
The PDF pages are provided as images and may contain English, Hindi, tables, merged cells, scanned text, or appended letters.

Extract the following user-requested attributes:
{fields}

Return strict JSON only with this exact shape:
{{
  "records": [
    {{
      "attribute_name": "value",
      "source_meta": {{
        "attribute_name": {{
          "pageNumber": 1,
          "text": "short exact source snippet copied from the PDF",
          "confidence": "high"
        }}
      }}
    }}
  ]
}}

Rules:
1. A document may contain one record or multiple records. If a table lists multiple people/entities/items, return one object per row/person/entity.
2. Every record must contain every requested attribute key exactly as written above.
3. If a value is missing or not explicitly recoverable, use "Null".
4. Apply shared context from headings, paragraphs, or merged cells to every relevant record.
5. Preserve dates and IDs carefully. If date normalization is obvious, use YYYY-MM-DD; otherwise return the date as written.
6. Every record must include "source_meta". It must contain one citation object for every requested attribute key exactly as written above.
7. Each citation object must include:
   - pageNumber: the 1-based page number where the value was read, or 0 if missing.
   - text: the shortest exact surrounding text snippet from the PDF that supports the extracted value, or "Null" if missing.
   - confidence: "high", "medium", "low", or "unknown".
8. Make the citation text as close as possible to the exact printed text, because it will be searched and highlighted in the PDF viewer.
9. Do not include markdown, explanations, comments, or extra keys outside "records".
"""


def _coerce_source_meta(raw_record: dict[str, Any], attributes: list[str]) -> dict[str, dict[str, int | str]]:
    raw_source_meta = raw_record.get("source_meta", {})
    if not isinstance(raw_source_meta, dict):
        raw_source_meta = {}

    source_meta: dict[str, dict[str, int | str]] = {}
    for attribute in attributes:
        value = raw_record.get(attribute, "Null")
        raw_source = raw_source_meta.get(attribute, {})
        if not isinstance(raw_source, dict):
            raw_source = {}

        raw_page_number = raw_source.get("pageNumber", 0)
        try:
            page_number = int(raw_page_number)
        except (TypeError, ValueError):
            page_number = 0

        source_text = raw_source.get("text")
        if source_text is None or source_text == "":
            source_text = "Null" if value in (None, "", "Null") else str(value)

        confidence = raw_source.get("confidence", "unknown")
        if str(confidence).lower() not in {"high", "medium", "low", "unknown"}:
            confidence = "unknown"

        source_meta[attribute] = {
            "pageNumber": max(page_number, 0),
            "text": str(source_text),
            "confidence": str(confidence).lower(),
        }

    return source_meta


def _coerce_records(data: dict[str, Any], attributes: list[str]) -> list[dict[str, Any]]:
    raw_records = data.get("records", [])
    if not isinstance(raw_records, list):
        raw_records = []

    records: list[dict[str, str]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue

        record: dict[str, Any] = {}
        for attribute in attributes:
            value = raw_record.get(attribute, "Null")
            if value is None or value == "":
                value = "Null"
            record[attribute] = str(value)

        record["source_meta"] = _coerce_source_meta(raw_record, attributes)
        records.append(record)

    return records


def _friendly_error(exc: Exception) -> str:
    error_text = str(exc)
    if "429" in error_text or "ResourceExhausted" in error_text:
        return "API Rate Limit Exceeded (429). Try fewer files at a time."
    return error_text


@dataclass
class ExtractionService:
    renderer: PdfRenderer
    llm_client: GeminiExtractionClient

    def extract_from_pdf(self, pdf_path: str, attributes: list[str]) -> list[dict[str, Any]]:
        if not attributes:
            raise ValueError("At least one extraction attribute is required.")

        images = self.renderer.render_to_images(pdf_path)
        prompt = build_dynamic_prompt(attributes)
        # Build a Pydantic schema matching the requested attributes and pass it
        # to Gemini as response_schema. This enables constrained decoding —
        # the model is guaranteed to emit valid JSON matching the schema without
        # any reasoning overhead, giving the same ~1s performance as the old
        # fixed-schema pipeline in extractor.py.
        schema = build_response_schema(attributes)
        data = self.llm_client.generate_json(prompt, images, response_schema=schema)
        records = _coerce_records(data, attributes)

        if not records:
            raise ValueError("Model returned no records for this document.")

        return records

    def extract_file_records(
        self,
        pdf_path: str,
        source_file: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        try:
            records = self.extract_from_pdf(pdf_path, attributes)
            return [
                {
                    "source_file": source_file,
                    **record,
                    "status": "Success",
                    "failure_reason": "",
                }
                for record in records
            ]
        except Exception as exc:
            return [
                {
                    "source_file": source_file,
                    **{attribute: "Null" for attribute in attributes},
                    "source_meta": {
                        attribute: {"pageNumber": 0, "text": "Null", "confidence": "unknown"}
                        for attribute in attributes
                    },
                    "status": "Failed",
                    "failure_reason": _friendly_error(exc),
                }
            ]


def build_extraction_service() -> ExtractionService:
    return ExtractionService(
        renderer=PdfRenderer(),
        llm_client=GeminiExtractionClient(),
    )

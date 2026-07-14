from pydantic import BaseModel, field_validator
from typing import Literal


class FieldExtraction(BaseModel):
    value: str
    source_text: str

    @field_validator("value", "source_text", mode="before")
    @classmethod
    def coerce_null(cls, v):
        if v is None or str(v).strip() == "":
            return "Null"
        return str(v).strip()


GroundingConfidence = Literal["high", "medium", "low", "unknown"]


class SourceMeta(BaseModel):
    text: str = "Null"
    confidence: GroundingConfidence = "unknown"


class FieldResult(BaseModel):
    value: str = "Null"
    source_meta: SourceMeta = SourceMeta()


class ExtractionRecord(BaseModel):
    source_file: str
    fields: dict[str, FieldResult]  # key = normalized field name
    status: Literal["success", "failed", "rejected"] = "success"
    failure_reason: str = ""


class ExtractionResponse(BaseModel):
    doc_type: str
    field_names: list[str]  # ordered, as requested
    records: list[ExtractionRecord]

from src.services.extraction_service import (
    build_dynamic_prompt,
    build_extraction_service,
    normalize_attributes,
)
from src.services.serializers import records_to_csv


def extract_dynamic_fields_from_pdf(
    filepath: str,
    attributes: list[str],
    retries: int = 3,
) -> list[dict[str, str]]:
    service = build_extraction_service()
    return service.extract_from_pdf(filepath, attributes)

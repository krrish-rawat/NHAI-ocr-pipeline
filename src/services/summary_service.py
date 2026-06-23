import re
from dataclasses import dataclass

from src.services.llm_client import GeminiExtractionClient
from src.services.pdf_renderer import PdfRenderer


SUMMARY_PROMPT = """
Analyze the uploaded PDF and generate a concise summary dashboard in 5-8 bullet points.
Do not extract form fields.
Do not mention or repeat any user-requested attributes or extracted attribute values.
Focus only on the overall document context, purpose, subject matter, key points, important observations, and possible actions or implications.
Keep each bullet point short, clear, and non-technical.
"""


def _clean_summary_points(summary_text: str) -> list[str]:
    points: list[str] = []

    for line in summary_text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            points.append(cleaned)

    if not points and summary_text.strip():
        points = [summary_text.strip()]

    return points[:8]


def _friendly_summary_error(exc: Exception) -> str:
    error_text = str(exc)
    if "429" in error_text or "ResourceExhausted" in error_text:
        return "API Rate Limit Exceeded (429). Try again after a short wait."
    if "timeout" in error_text.lower() or "deadline" in error_text.lower():
        return "Summary generation timed out. Try a smaller PDF or retry."
    return error_text


@dataclass
class SummaryService:
    renderer: PdfRenderer
    llm_client: GeminiExtractionClient

    def summarize_pdf(self, pdf_path: str) -> list[str]:
        images = self.renderer.render_to_images(pdf_path)
        if not images:
            raise ValueError("The uploaded PDF has no readable pages.")

        summary_text = self.llm_client.generate_text(SUMMARY_PROMPT, images)
        summary_points = _clean_summary_points(summary_text)

        if not summary_points:
            raise ValueError("Model returned no summary for this document.")

        return summary_points

    def summarize_file(self, pdf_path: str) -> dict[str, list[str] | str]:
        try:
            return {"summary_points": self.summarize_pdf(pdf_path)}
        except Exception as exc:
            return {
                "summary_points": [],
                "error": _friendly_summary_error(exc),
            }


def build_summary_service() -> SummaryService:
    return SummaryService(
        renderer=PdfRenderer(),
        llm_client=GeminiExtractionClient(),
    )

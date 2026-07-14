"""FastAPI API routes for the NHAI PDF Data Extraction rebuild.

Route handlers contain NO business logic — they only:
1. Validate the HTTP request
2. Call the pipeline
3. Serialize and return the result

All business logic lives in ExtractionPipeline.run().
"""
import logging
import os
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from src.services.pipeline import ExtractionPipeline
from src.services.serializers import records_to_csv, records_to_json
from src.services.settings import AppSettings
from src.services.utils import deduplicate_fields

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF-"


def _split_fields(raw: str) -> list[str]:
    """Split a comma-or-newline-separated field string into individual field names."""
    parts = re.split(r"[\n,]+", raw)
    return deduplicate_fields([p for p in parts if p.strip()])


def create_router(
    pipeline: ExtractionPipeline,
    settings: AppSettings,
    templates: Jinja2Templates,
) -> APIRouter:
    """Create and return the API router, injecting dependencies."""
    router = APIRouter()

    # ── GET / ──────────────────────────────────────────────────────────────────

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request, "index.html")

    # ── GET /health ────────────────────────────────────────────────────────────

    @router.get("/health")
    async def health():
        return {"status": "ok", "mistral_key_present": bool(settings.mistral_api_key)}

    # ── POST /classify ─────────────────────────────────────────────────────────

    @router.post("/classify")
    async def classify(file: UploadFile = File(...)):
        """Phase 1 only: classify a document without extracting fields."""
        # Read and validate file
        content = await file.read()
        if not content.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="File is too large.")

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Run OCR + classify only
            ocr_text = await run_in_threadpool(pipeline.ocr.extract_text, tmp_path)
            doc_type = pipeline.classifier.classify(ocr_text)
            return {"doc_type": doc_type}
        except Exception as exc:
            logger.warning("Classify endpoint error: %s", exc)
            return {"doc_type": "other"}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ── POST /extract ──────────────────────────────────────────────────────────

    @router.post("/extract")
    async def extract(
        file: UploadFile = File(...),
        fields: str = Form(...),
        output_format: str = Form("json"),
        force_extract: str = Form("false"),
    ):
        """Full extraction pipeline: OCR → classify → gate → extract → serialize."""
        # Validate output format
        if output_format not in ("json", "csv"):
            raise HTTPException(
                status_code=400,
                detail="output_format must be 'json' or 'csv'.",
            )

        # Validate fields
        field_names = _split_fields(fields)
        if not field_names:
            raise HTTPException(
                status_code=400,
                detail="Provide at least one field name.",
            )

        # Read and validate file
        content = await file.read()
        if not content.startswith(_PDF_MAGIC):
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="File is too large.")

        # Save to temp file
        source_file = file.filename or "uploaded.pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            should_force = force_extract.lower() in ("true", "1", "yes")

            response = await run_in_threadpool(
                pipeline.run,
                tmp_path,
                source_file,
                field_names,
                should_force,
            )
        except Exception as exc:
            logger.error("Unexpected pipeline error: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Extraction failed. Please try again.",
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if output_format == "csv":
            csv_content = records_to_csv(response, field_names)
            return Response(
                content=csv_content.encode("utf-8-sig"),
                media_type="text/csv",
                headers={
                    "Content-Disposition": 'attachment; filename="extracted.csv"'
                },
            )

        json_content = records_to_json(response, field_names)
        return Response(content=json_content, media_type="application/json")

    return router

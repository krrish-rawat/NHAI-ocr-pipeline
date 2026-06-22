import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from src.services.extraction_service import (
    build_extraction_service,
    normalize_attributes,
)
from src.services.serializers import records_to_csv, records_to_json_payload
from src.services.settings import settings

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="NHAI PDF Parser")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
extraction_service = build_extraction_service()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


def _validate_pdf_upload(upload: UploadFile) -> None:
    filename = upload.filename or ""
    content_type = upload.content_type or ""

    if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Only PDF uploads are supported: {filename or 'unnamed file'}",
        )


async def _save_upload_to_temp_pdf(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        total_size = 0
        while chunk := await upload.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail="Uploaded PDF is too large.")
            tmp.write(chunk)
        return tmp.name


@app.post("/extract")
async def extract(
    files: list[UploadFile] = File(...),
    attributes: str = Form(...),
    output_format: str = Form("json"),
):
    requested_attributes = normalize_attributes(attributes)
    if not requested_attributes:
        raise HTTPException(status_code=400, detail="Provide at least one attribute.")

    if output_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Output format must be json or csv.")

    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF file.")

    all_records: list[dict[str, str]] = []

    for upload in files:
        source_file = upload.filename or "uploaded.pdf"
        temp_path = ""

        try:
            _validate_pdf_upload(upload)
            temp_path = await _save_upload_to_temp_pdf(upload)
            file_records = await run_in_threadpool(
                extraction_service.extract_file_records,
                temp_path,
                source_file,
                requested_attributes,
            )
            all_records.extend(file_records)
        except Exception as exc:
            all_records.append(
                {
                    "source_file": source_file,
                    **{attribute: "Null" for attribute in requested_attributes},
                    "status": "Failed",
                    "failure_reason": str(exc),
                }
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    if output_format == "csv":
        csv_output = records_to_csv(all_records, requested_attributes)
        return Response(
            content=csv_output,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="extracted_records.csv"'},
        )

    return Response(
        content=records_to_json_payload(all_records, requested_attributes),
        media_type="application/json",
    )

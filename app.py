"""NHAI PDF Data Extraction — FastAPI application entry point (rebuild).

Importing settings at module level triggers startup validation:
if MISTRAL_API_KEY is absent, the process fails immediately with a clear error.
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import settings FIRST — this triggers fail-fast validation at startup.
# If MISTRAL_API_KEY is absent, this import raises ValueError and the
# server refuses to start rather than failing silently on the first request.
from src.services.settings import settings
from src.services.pipeline import build_pipeline
from src.api.routes import create_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="NHAI PDF Data Extraction",
    description="Extract structured fields from NHAI government PDFs.",
    version="2.0.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Templates
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Build the extraction pipeline (wires OCR, classifier, extractor from settings)
pipeline = build_pipeline(settings)

# Include routes
api_router = create_router(pipeline=pipeline, settings=settings, templates=templates)
app.include_router(api_router)

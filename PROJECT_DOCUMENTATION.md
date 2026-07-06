# 📚 NHAI PDF Parser - Complete Project Documentation

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Core Components](#core-components)
6. [Feature: Document Validation System](#feature-document-validation-system)
7. [API Endpoints](#api-endpoints)
8. [Installation & Setup](#installation--setup)
9. [Configuration](#configuration)
10. [Usage Guide](#usage-guide)
11. [Data Models](#data-models)
12. [Processing Pipeline](#processing-pipeline)
13. [Error Handling](#error-handling)
14. [Performance Optimization](#performance-optimization)
15. [Document Types](#document-types)
16. [Frontend Implementation](#frontend-implementation)
17. [Backend Services](#backend-services)

---

## Project Overview

### What Is This Project?

The **NHAI PDF Parser** is a sophisticated document processing system designed to extract structured data from NHAI (National Highways Authority of India) project documents. It analyzes PDF files, classifies document types, validates them against a whitelist, extracts relevant data fields, and generates AI-powered summaries.

### Purpose

- Extract data from NHAI project documents (LOA, CC, PCC, Financial Closure, Debarment Records, etc.)
- Validate document types before processing
- Generate structured data outputs (JSON/CSV)
- Create intelligent summaries of document content
- Prevent extraction from invalid/unsupported documents

### Key Features

✅ **Document Type Classification** - AI-powered document classification  
✅ **Pre-Extraction Validation** - Blocks invalid documents before extraction  
✅ **Structured Data Extraction** - Extracts specified attributes from PDFs  
✅ **Multiple Output Formats** - JSON and CSV export options  
✅ **AI-Powered Summaries** - Generates summaries using Gemini LLM  
✅ **OCR Support** - Handles both text and scanned PDFs  
✅ **Batch Processing** - Processes multiple files concurrently  
✅ **Web Interface** - User-friendly web UI for document upload  
✅ **RESTful API** - Complete API for programmatic access  

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Browser                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           Frontend (Vanilla JavaScript)         │   │
│  │  - Document upload form                         │   │
│  │  - Validation gate (pre-render check)           │   │
│  │  - Results display                              │   │
│  │  - Warning banner for invalid docs              │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────┘
                   │ HTTP (REST API)
                   ▼
┌─────────────────────────────────────────────────────────┐
│            Backend (FastAPI + Python)                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  API Layer (FastAPI)                            │   │
│  │  - /extract - Data extraction                   │   │
│  │  - /summarize - Summary generation              │   │
│  │  - /test-classify - Classification testing      │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Extraction Service                             │   │
│  │  - Phase 1: Document Classification             │   │
│  │  - Phase 2: Validation Check                    │   │
│  │  - Phase 3: OCR Processing                      │   │
│  │  - Phase 4: LLM-based Extraction                │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Summary Service                                │   │
│  │  - Extracts key points from document            │   │
│  │  - Uses Gemini LLM                              │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  LLM Client (Gemini Integration)                │   │
│  │  - Classification prompts                       │   │
│  │  - Extraction prompts                           │   │
│  │  - Summary prompts                              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│              External Services                          │
│  - Google Gemini API (Classification & Extraction)      │
│  - PyMuPDF (PDF parsing)                               │
│  - pytesseract (OCR for scanned PDFs)                   │
└─────────────────────────────────────────────────────────┘
```

### Request Flow

1. User uploads PDF via web UI
2. Frontend sends HTTP POST to `/extract` endpoint
3. Backend validates PDF format
4. **Phase 1**: Classify document type using Gemini
5. **Phase 2**: Check if type is in whitelist
6. If invalid → Return error with `document_validity: {is_valid: false}`
7. If valid → Proceed to extraction
8. **Phase 3**: Extract text and metadata using OCR
9. **Phase 4**: Use Gemini LLM to extract structured data
10. Frontend receives response with validation status
11. Frontend checks `document_validity` before rendering results
12. If valid → Show results and generate summary
13. If invalid → Show warning banner, suppress results

---

## Technology Stack

### Backend

| Technology | Purpose |
|-----------|---------|
| **Python 3.10+** | Primary language |
| **FastAPI** | Web framework for REST API |
| **Uvicorn** | ASGI server |
| **Pydantic v2** | Data validation |
| **Google Generativeai** | Gemini LLM API |
| **PyMuPDF (fitz)** | PDF parsing and rendering |
| **pytesseract** | OCR (Tesseract wrapper) |
| **Pillow (PIL)** | Image processing |
| **pandas** | Data manipulation |
| **rapidfuzz** | Fuzzy string matching |
| **python-dotenv** | Environment variables |

### Frontend

| Technology | Purpose |
|-----------|---------|
| **HTML5** | Markup |
| **CSS3** | Styling |
| **Vanilla JavaScript** | Frontend logic |
| **Fetch API** | HTTP requests |
| **Jinja2 Templates** | Server-side template rendering |

### Infrastructure

| Component | Version |
|-----------|---------|
| OS | macOS (darwin) |
| Shell | zsh |
| Port | 8000 |

---

## Project Structure

```
Nhai-pdf-parser/
├── app.py                           # Main FastAPI application
├── requirements.txt                 # Python dependencies
├── .env                             # Environment variables (Gemini API key)
├── .gitignore                       # Git ignore rules
│
├── src/                             # Source code
│   ├── __init__.py
│   └── services/                    # Core services
│       ├── __init__.py
│       ├── extraction_service.py    # PDF extraction logic
│       ├── llm_client.py            # Gemini API integration
│       ├── pdf_renderer.py          # PDF rendering
│       ├── summary_service.py       # Summary generation
│       ├── settings.py              # Configuration
│       └── serializers.py           # Data serialization (JSON/CSV)
│
├── static/                          # Frontend assets
│   ├── app.js                       # JavaScript frontend logic
│   ├── styles.css                   # CSS styling
│   └── nhai-logo.jpg                # NHAI logo
│
├── templates/                       # HTML templates
│   ├── index.html                   # Main application page
│   └── test-validation.html         # Testing/validation page
│
└── Documentation/                   # Project documentation
    ├── PROJECT_DOCUMENTATION.md     # This file
    ├── WHITELIST_UPDATE_COMPLETE.md # Whitelist changes
    ├── ACCEPTED_DOCUMENT_TYPES.md   # Document types reference
    ├── IMPLEMENTATION_CHECKLIST.md  # Implementation status
    └── ... (other docs)
```

---

## Core Components

### 1. FastAPI Application (`app.py`)

**Purpose:** Main application entry point and API endpoint definitions

**Key Functions:**

- `index()` - Serves the main web UI
- `extract()` - Main extraction endpoint
- `summarize()` - Summary generation endpoint
- `test_classify()` - Document classification testing endpoint
- `_process_single_upload()` - Processes one uploaded file
- `_summarize_single_upload()` - Generates summary for uploaded file

**Key Features:**

- Async/await for concurrent processing
- Multi-file upload support
- JSON and CSV output formats
- Error handling and validation

### 2. Extraction Service (`extraction_service.py`)

**Purpose:** Core PDF processing and data extraction logic

**Key Classes:**

- `ExtractionService` - Main extraction orchestrator
- `SourceMeta` - Metadata about extracted data
- `OCRIndex` - OCR caching mechanism

**Key Methods:**

- `extract_file_records()` - Full extraction pipeline (Phase 1-4)
- `classify_document()` - Document type classification
- `extract_from_pdf()` - LLM-based data extraction
- `_is_accepted_doc_type()` - Validation against whitelist

**Whitelist (6 Accepted Types):**

```python
_ACCEPTED_DOC_PATTERNS = [
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
    "debarment records",
    "debarment of individuals",
    # ... partial patterns and abbreviations
]

_ACCEPTED_DOC_TOKENS = frozenset([
    "loa", "cc", "pcc", "debarment"
])
```

### 3. LLM Client (`llm_client.py`)

**Purpose:** Integration with Google Gemini API

**Key Functions:**

- Classification prompts for document type detection
- Extraction prompts for structured data extraction
- Summary prompts for document summaries
- Constrained output for structured responses

### 4. Summary Service (`summary_service.py`)

**Purpose:** AI-powered document summarization

**Features:**

- Extracts key points from documents
- Uses Gemini LLM for intelligent summarization
- Timeout handling (configurable)

### 5. PDF Renderer (`pdf_renderer.py`)

**Purpose:** PDF rendering and image generation

**Features:**

- Converts PDF pages to images
- Supports base64 encoding
- Used for document preview in UI

### 6. Settings (`settings.py`)

**Purpose:** Application configuration

**Key Settings:**

```python
max_upload_bytes: int = 50 * 1024 * 1024  # 50MB
summary_timeout_seconds: int = 120         # 2 minutes
gemini_model: str = "gemini-2.0-flash"     # LLM model
```

### 7. Serializers (`serializers.py`)

**Purpose:** Data format conversion

**Functions:**

- `records_to_csv()` - Convert records to CSV format
- `records_to_json_payload()` - Convert records to JSON

---

## Feature: Document Validation System

### Overview

The Document Validation System is a comprehensive pre-extraction gate that validates documents before processing. It prevents extraction and summary generation for invalid documents.

### Implementation Phases

**Phase 1: Classification**
- Classify document type using Gemini
- Detect: LOA, CC, PCC, Financial Closure, Debarment Records, Debarment of Individuals, or Other

**Phase 2: Validation**
- Check if classified type matches whitelist
- Return early if invalid (no extraction, no API costs)

**Phase 3: Extraction**
- Only runs if Phase 1 passes
- Extracts structured data
- Generates metadata

**Phase 4: Validation Response**
- Builds `document_validity` object
- Includes: `is_valid`, `detected_type`, `confidence`, `message`

### API Response Structure

```json
{
  "attributes": ["tender_id", "location"],
  "records": [
    {
      "tender_id": "NHAI/TEN/2024/001",
      "location": "Maharashtra",
      "_pdfUrl": "blob:...",
      "status": "Success",
      "source_file": "document.pdf"
    }
  ],
  "document_validity": {
    "is_valid": true,
    "detected_type": "Letter of Award (LOA)",
    "confidence": "high",
    "message": null
  }
}
```

### Frontend Validation Gate

Located in `/static/app.js` (lines 1162-1195):

```javascript
// Check document_validity response
const validity = data.document_validity ?? null;
const shouldRenderResults = DocValidity.evaluate(validity);

if (!shouldRenderResults) {
  // HARD STOP: Return early, no summary generated
  resultForm.hidden = true;
  resetSummaryDashboard();
  return;
}

// Proceed with results and summary
showResultPanel(records);
summarizeSelectedFiles();
```

---

## API Endpoints

### 1. GET `/`

**Purpose:** Serve main web UI

**Response:** HTML page with document upload form

### 2. POST `/extract`

**Purpose:** Extract data from PDF documents

**Parameters:**

- `files` (file, required): One or more PDF files
- `attributes` (string, required): Comma-separated list of data fields to extract
- `output_format` (string, optional): "json" (default) or "csv"

**Request Example:**

```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@document.pdf" \
  -F "attributes=tender_id,location,amount" \
  -F "output_format=json"
```

**Response:** JSON object with extracted records and validation status

### 3. POST `/summarize`

**Purpose:** Generate AI summary of document

**Parameters:**

- `file` (file, required): Single PDF file

**Request Example:**

```bash
curl -X POST http://localhost:8000/summarize \
  -F "file=@document.pdf"
```

**Response:**

```json
{
  "source_file": "document.pdf",
  "summary_points": [
    "Point 1",
    "Point 2",
    "Point 3"
  ]
}
```

### 4. POST `/test-classify`

**Purpose:** Test document classification (debugging)

**Parameters:**

- `file` (file, required): Single PDF file

**Response:**

```json
{
  "classified_as": "Letter of Award (LOA)",
  "is_valid": true,
  "message": "Classification successful"
}
```

### 5. GET `/test-validation`

**Purpose:** Serve validation testing page

**Response:** HTML page for testing document validation

---

## Installation & Setup

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Tesseract OCR (for scanned PDFs)
- Google Gemini API key

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd Nhai-pdf-parser
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Install Tesseract OCR

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**Windows:**
- Download from: https://github.com/UB-Mannheim/tesseract/wiki
- Install to default location: `C:\Program Files\Tesseract-OCR`

### Step 5: Configure Environment Variables

Create `.env` file in project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Get API key from: https://ai.google.dev/

### Step 6: Run Application

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at: http://localhost:8000

---

## Configuration

### Environment Variables

**Required:**

```env
GEMINI_API_KEY=<your-gemini-api-key>
```

**Optional:**

```env
# Settings (configured in src/services/settings.py)
MAX_UPLOAD_BYTES=52428800           # 50MB
SUMMARY_TIMEOUT_SECONDS=120          # 2 minutes
GEMINI_MODEL=gemini-2.0-flash        # LLM model
TESSERACT_PATH=/usr/local/bin/tesseract  # Tesseract location (auto-detected on macOS)
```

### Application Settings

File: `src/services/settings.py`

```python
max_upload_bytes: int = 50 * 1024 * 1024
summary_timeout_seconds: int = 120
gemini_model: str = "gemini-2.0-flash"
```

---

## Usage Guide

### Via Web UI

1. **Open Browser:** http://localhost:8000
2. **Upload PDF:** Drag and drop or click to select file
3. **Enter Attributes:** Type comma-separated field names (e.g., "tender_id, location, amount")
4. **Select Format:** Choose JSON or CSV
5. **Click Extract:** System will classify, validate, and extract
6. **View Results:** 
   - ✅ If valid: See extraction results and summary
   - ⚠️ If invalid: See warning banner asking to upload valid document
7. **Download:** Use provided download buttons

### Via API (cURL)

**Extract Data:**

```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@document.pdf" \
  -F "attributes=tender_id,location" \
  -F "output_format=json" | python3 -m json.tool
```

**Generate Summary:**

```bash
curl -X POST http://localhost:8000/summarize \
  -F "file=@document.pdf" | python3 -m json.tool
```

**Test Classification:**

```bash
curl -X POST http://localhost:8000/test-classify \
  -F "file=@document.pdf" | python3 -m json.tool
```

### Via Python

```python
import requests

# Upload and extract
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/extract",
        files={"files": f},
        data={
            "attributes": "tender_id,location",
            "output_format": "json"
        }
    )
    
result = response.json()
print(result)
```



---

## Data Models

### SourceMeta (Metadata for Extracted Fields)

```python
class SourceMeta:
    pageNumber: int          # Page number where data was found
    text: str               # Extracted text snippet
    confidence: str         # Confidence level: "high", "medium", "low", "unknown"
    
    def to_dict(self) -> dict
```

### Extraction Record

```python
{
    "source_file": "document.pdf",
    "tender_id": "NHAI/TEN/2024/001",
    "location": "Maharashtra",
    "source_meta": {
        "tender_id": {
            "pageNumber": 1,
            "text": "NHAI/TEN/2024/001 Tender",
            "confidence": "high"
        },
        "location": {
            "pageNumber": 1,
            "text": "Location: Maharashtra",
            "confidence": "medium"
        }
    },
    "status": "Success",
    "failure_reason": "",
    "_pdfUrl": "blob:http://localhost:8000/..."
}
```

### Document Validity Object

```python
{
    "is_valid": bool,                          # true/false
    "detected_type": str,                      # Document classification
    "confidence": str,                         # "high", "medium", "low"
    "message": str | None                      # Error message if applicable
}
```

---

## Processing Pipeline

### Step-by-Step Process

```
1. USER UPLOADS PDF
   └─ Browser validates file (PDF only)
   └─ File sent to /extract endpoint

2. SERVER RECEIVES UPLOAD
   └─ Validate PDF format and size
   └─ Save to temporary file
   └─ Extract requested attributes from form

3. PHASE 1: QUICK CLASSIFICATION
   ├─ Use Gemini to classify document type
   ├─ Log classification result
   ├─ Check against whitelist (_ACCEPTED_DOC_PATTERNS)
   └─ If INVALID:
      └─ Return early with document_validity: {is_valid: false}
      └─ NO extraction, NO API costs
   └─ If VALID: Proceed to Phase 2

4. PHASE 2: OCR PROCESSING
   ├─ Extract text from PDF (PyMuPDF)
   ├─ If scanned PDF: Run Tesseract OCR
   ├─ Build OCR index for faster lookups
   └─ Cache results for reuse

5. PHASE 3: LLM EXTRACTION
   ├─ Create extraction prompt with:
      ├─ PDF text content
      ├─ Requested attributes
      ├─ Formatting instructions
   ├─ Send to Gemini with constrained output
   ├─ Parse JSON response
   ├─ Include page numbers and confidence scores
   └─ Return structured records

6. PHASE 4: BUILD RESPONSE
   ├─ Attach metadata to each record
   ├─ Add status ("Success", "Failed", "Blocked")
   ├─ Include document_validity object
   ├─ Format as JSON or CSV
   └─ Return to client

7. BROWSER RECEIVES RESPONSE
   ├─ Extract records and document_validity
   ├─ Call DocValidity.evaluate(validity)
   ├─ If is_valid: false
   │  ├─ Show amber warning banner
   │  ├─ Hide results
   │  ├─ Suppress summary
   │  └─ Return early (HARD STOP)
   └─ If is_valid: true
      ├─ Show extraction results
      ├─ Call /summarize endpoint
      ├─ Display summary points
      └─ Done!

8. SUMMARY GENERATION (Only for valid docs)
   ├─ Send PDF to /summarize endpoint
   ├─ Generate summary using Gemini
   ├─ Extract key points (5-10 points)
   └─ Display in UI

9. CLEANUP
   └─ Delete temporary PDF file
   └─ Clear OCR cache
```

---

## Error Handling

### Error Types

**1. Upload Errors**
- Status: 400 Bad Request
- Reasons: Not a PDF, too large, missing file
- Response: HTTP error with detail message

**2. Validation Errors**
- Status: 400 Bad Request
- Reasons: No attributes provided, invalid format
- Response: HTTP error with detail message

**3. Processing Errors**
- Status: 200 OK (with error in record)
- Reasons: PDF corrupted, extraction failed
- Response: Record with status="Failed", failure_reason set

**4. Classification Errors**
- Status: 200 OK
- Reasons: Cannot classify document
- Response: document_validity with is_valid=false

**5. Summary Timeout**
- Status: 200 OK (with error in response)
- Reasons: Summary generation took too long
- Response: summary_points=[], error message set

### Error Response Examples

**Extraction Error:**

```json
{
  "attributes": ["tender_id"],
  "records": [
    {
      "source_file": "document.pdf",
      "tender_id": "Null",
      "source_meta": {
        "tender_id": {
          "pageNumber": 0,
          "text": "Null",
          "confidence": "unknown"
        }
      },
      "status": "Failed",
      "failure_reason": "PDF parsing failed: Corrupted PDF structure"
    }
  ],
  "document_validity": {
    "is_valid": false,
    "detected_type": "Error",
    "confidence": "high",
    "message": "Upload processing failed: ..."
  }
}
```

**Validation Error:**

```json
{
  "detail": "Provide at least one attribute."
}
```

---

## Performance Optimization

### 1. Concurrent Processing

**Feature:** Multiple files processed in parallel

```python
results = await asyncio.gather(
    *[_process_single_upload(upload, attrs) for upload in files]
)
```

**Benefit:** N files take ~time of slowest, not N × time

### 2. OCR Caching

**Feature:** OCR results cached per document

```python
ocr_index = self._get_or_build_ocr_index(pdf_path)
# Reuse ocr_index for multiple attribute extractions
_ocr_cache.evict(pdf_path)  # Clean up after use
```

**Benefit:** Avoid redundant OCR on same document

### 3. Early Abort (Phase 1)

**Feature:** Invalid documents rejected before extraction

**Benefit:** 
- Saves API calls to Gemini
- Reduces processing time
- Lower costs

### 4. Thread Pool Execution

**Feature:** CPU-intensive PDF operations run in thread pool

```python
await run_in_threadpool(
    extraction_service.extract_file_records,
    temp_path,
    source_file,
    requested_attributes,
)
```

**Benefit:** Non-blocking async execution

### 5. Timeout Handling

**Feature:** Summary generation has configurable timeout

```python
result = await asyncio.wait_for(
    run_in_threadpool(summary_service.summarize_file, temp_path),
    timeout=settings.summary_timeout_seconds,  # Default: 120 seconds
)
```

**Benefit:** Prevent hung requests

---

## Document Types

### Accepted Document Types (6 Total)

#### 1. Letter of Award (LOA)
- **Aliases:** "loa", "letter of award"
- **Typical Fields:** tender_id, awarded_to, contract_value, location
- **Status:** ✅ Accepted

#### 2. Completion Certificate (CC)
- **Aliases:** "cc", "completion certificate"
- **Typical Fields:** tender_id, contractor, completion_date, final_amount
- **Status:** ✅ Accepted

#### 3. Provisional Completion Certificate (PCC)
- **Aliases:** "pcc", "provisional cc", "provisional completion certificate"
- **Typical Fields:** tender_id, work_description, pcc_amount, issues
- **Status:** ✅ Accepted

#### 4. Financial Closure
- **Aliases:** "financial closure"
- **Typical Fields:** tender_id, total_expenditure, fund_source, closure_date
- **Status:** ✅ Accepted

#### 5. Debarment Records (NEW)
- **Aliases:** "debarment records"
- **Typical Fields:** company_name, debarment_reason, debarment_from_date, debarment_to_date
- **Status:** ✅ Accepted

#### 6. Debarment of Individuals (NEW)
- **Aliases:** "debarment of individuals"
- **Typical Fields:** individual_name, designation, debarment_reason, effective_date
- **Status:** ✅ Accepted

### Classification Matching (3 Levels)

**Level 1: Full Phrase Match (Most Specific)**
```
Pattern List: ["letter of award (loa)", "completion certificate (cc)", ...]
Input: "Letter of Award (LOA)"
Match: YES ✅ ACCEPTED
```

**Level 2: Substring Match**
```
Pattern List: ["letter of award", "completion certificate", ...]
Input: "Official Letter of Award Document 2024"
Check: Does string contain pattern?
Match: YES ✅ ACCEPTED
```

**Level 3: Token Match (Least Specific)**
```
Token List: ["loa", "cc", "pcc", "debarment"]
Input: "Debarment Notice Form"
Tokens: ["debarment", "notice", "form"]
Match: Contains "debarment" ✅ ACCEPTED
```

### Rejected Document Types

- Invoice
- ACR Form
- Receipt
- Tax Document
- Bank Statement
- Generic Contract
- Any non-NHAI document

---

## Frontend Implementation

### Architecture

**Framework:** Vanilla JavaScript (no frameworks)  
**Template Engine:** Jinja2 (for HTML)  
**Styling:** Custom CSS  

### Key JavaScript Modules

#### 1. DocValidity Module (lines 60-209)

**Purpose:** Validates document type and shows warning banner

**Key Function:**
```javascript
DocValidity.evaluate(validity) -> boolean
// Returns true if results should be rendered, false to suppress
```

**Features:**
- Shows amber warning banner for invalid documents
- Provides "Upload Correct Document" button
- Provides "Force Extract Anyway" override button
- Type label mapping for display

#### 2. Validation Gate (lines 1162-1195)

**Purpose:** Pre-render hard gate before showing results

**Logic:**
```javascript
if (!shouldRenderResults) {
  // HARD STOP: Return early
  resultForm.hidden = true;
  resetSummaryDashboard();
  return;  // Critical: Prevents summary generation
}
```

**Critical Requirement:** Ensures summary never starts for invalid documents

#### 3. Progress Bar (lines 200+)

**Purpose:** Visual feedback during extraction

**Features:**
- Animated progress indicator
- Status messages
- Percentage completion

#### 4. File Upload Handler

**Purpose:** Handles file selection and upload

**Features:**
- Drag-and-drop support
- File validation (PDF only)
- Multi-file support
- Progress tracking

#### 5. Results Display

**Purpose:** Shows extraction results in table format

**Features:**
- Pagination support
- Sortable columns
- Export to CSV
- PDF preview

#### 6. Summary Display

**Purpose:** Shows AI-generated summary

**Features:**
- Bullet point list
- Copy to clipboard
- Summary refresh

### CSS Styling

**Color Scheme:**
- Primary: #F59E0B (Amber/Orange)
- Secondary: #CBD5E1 (Slate)
- Background: #FFFDF5 (Cream)
- Error: #DC2626 (Red)
- Success: #16A34A (Green)

**Key Classes:**
- `.doc-validity-banner--block` - Invalid document warning
- `.doc-validity-banner--notice` - Low confidence notice
- `.banner-action--primary` - Primary action button
- `.banner-action--secondary` - Secondary action button

---

## Backend Services

### ExtractionService

**Responsibility:** Orchestrate PDF processing pipeline

**Key Methods:**

```python
extract_file_records(pdf_path, source_file, attributes)
  → Returns dict with "records" and "document_validity"

classify_document(pdf_path)
  → Returns document type string

extract_from_pdf(pdf_path, attributes, ocr_index)
  → Returns (document_type, records) tuple

_get_or_build_ocr_index(pdf_path)
  → Returns cached OCR index or builds new one

_friendly_error(exception)
  → Returns user-friendly error message
```

### SummaryService

**Responsibility:** Generate AI summaries

**Key Methods:**

```python
summarize_file(pdf_path)
  → Returns dict with "summary_points" list

_extract_text_from_pdf(pdf_path)
  → Returns document text content
```

### LLMClient

**Responsibility:** Manage Gemini API integration

**Key Methods:**

```python
classify_document(text)
  → Classifies document type

extract_data(text, attributes)
  → Extracts structured data

generate_summary(text)
  → Generates document summary
```

### Prompts Used

**Classification Prompt:**

The system uses constrained prompts that force Gemini to:
1. Analyze document structure and content
2. Determine document type from whitelist
3. Return JSON with document_type field
4. Include confidence assessment

**Extraction Prompt:**

The system creates dynamic prompts that:
1. Provide PDF text content
2. List requested attributes
3. Specify JSON output format
4. Request page numbers and confidence

**Summary Prompt:**

The system instructs Gemini to:
1. Extract 5-10 key points
2. Summarize main content
3. Format as bullet points
4. Use concise language

---

## Deployment

### Production Deployment

**Recommended Setup:**

1. **Web Server:** nginx (reverse proxy)
2. **Application Server:** uvicorn (with gunicorn/supervisor)
3. **Database:** Not required (stateless)
4. **Cache:** Optional (Redis for OCR caching)
5. **Load Balancer:** nginx or HAProxy

**Docker Deployment:**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose:**

```yaml
version: '3'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    volumes:
      - ./logs:/app/logs
```

---

## Troubleshooting

### Common Issues

**Issue: "Gemini API Key Invalid"**
- Solution: Check `.env` file, ensure key is valid
- Verify: `echo $GEMINI_API_KEY`

**Issue: "Tesseract not found"**
- Solution: Install Tesseract OCR
- macOS: `brew install tesseract`
- Linux: `sudo apt-get install tesseract-ocr`

**Issue: "PDF too large"**
- Solution: Increase `MAX_UPLOAD_BYTES` in settings
- Default: 50MB
- Recommended: 100MB max

**Issue: "Summary timeout"**
- Solution: Increase `SUMMARY_TIMEOUT_SECONDS`
- Default: 120 seconds
- Recommended: 180-300 seconds for large documents

**Issue: "Invalid document still showing results"**
- Solution: Hard refresh browser cache
- macOS: `Cmd + Shift + R`
- Windows: `Ctrl + F5`

---

## Best Practices

### For Users

1. **Upload high-quality PDFs** - Better OCR results
2. **Use standard attribute names** - Faster extraction
3. **Test with /test-classify first** - Verify document type
4. **Check validation response** - Understand why docs are blocked

### For Developers

1. **Use type hints** - Python typing for safety
2. **Add logging** - Track processing pipeline
3. **Handle exceptions** - User-friendly error messages
4. **Test with test-classify** - Debug classification issues
5. **Cache OCR results** - Avoid redundant processing
6. **Use thread pools** - Don't block async operations

### For Operations

1. **Monitor API usage** - Track Gemini API calls
2. **Set up logging** - Debug production issues
3. **Use environment variables** - Never hardcode secrets
4. **Implement rate limiting** - Prevent API abuse
5. **Regular backups** - Keep code safe
6. **Test error scenarios** - Ensure graceful failure

---

## Future Enhancements

### Planned Features

1. **Database Integration** - Store extraction history
2. **Authentication** - User login and access control
3. **Advanced Caching** - Redis for distributed caching
4. **Batch Processing** - Scheduled document processing
5. **Custom Prompts** - User-defined extraction templates
6. **Multi-language Support** - Non-English documents
7. **Document Versioning** - Track document changes
8. **Analytics Dashboard** - Processing statistics
9. **Export Templates** - Custom export formats
10. **Webhook Notifications** - Integration with external systems

---

## References

### External Documentation

- **FastAPI:** https://fastapi.tiangolo.com/
- **Google Gemini API:** https://ai.google.dev/
- **PyMuPDF:** https://pymupdf.readthedocs.io/
- **pytesseract:** https://pypi.org/project/pytesseract/
- **pydantic:** https://docs.pydantic.dev/

### Related Documents

- `WHITELIST_UPDATE_COMPLETE.md` - Whitelist changes
- `ACCEPTED_DOCUMENT_TYPES.md` - Supported document types
- `IMPLEMENTATION_CHECKLIST.md` - Development checklist
- `VALIDATION_CODE_REFERENCE.md` - Code locations
- `FINAL_STATUS_REPORT.md` - Project status

---

## Support & Contact

**Issues:** Please file issues in the repository  
**Questions:** Check documentation first  
**Contributions:** Follow the development setup guide  

---

**Last Updated:** July 3, 2024  
**Version:** 2.0  
**Status:** Production Ready ✅


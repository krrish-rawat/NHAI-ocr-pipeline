# Validation System - Code Reference

## Complete Implementation Map

### Backend: Phase 1 Classification (extraction_service.py)

**Location:** `/src/services/extraction_service.py` lines 694-783

```python
async def extract_file_records(
    pdf_path: str, requested_attrs: Sequence[str]
) -> dict[str, object]:
    """
    Returns: Dictionary with "records" (list) and "document_validity" (dict)
    """
    
    # PHASE 1: Quick classification
    document_type = self.classify_document(pdf_path)
    is_valid = _is_accepted_doc_type(document_type)
    
    logger.info(f"Is Valid: {is_valid}")
    
    # BUILD EARLY ABORT RESPONSE if invalid
    if not is_valid:
        logger.warning("PHASE 1 BLOCKED: Document rejected")
        logger.warning(f"Type: '{document_type}' not in accepted types")
        
        return {
            "records": [
                {
                    "status": "Blocked",
                    "reason": f"Type: '{document_type}' not in accepted types",
                    "message": "Blocking extraction and returning validation error"
                }
            ],
            "document_validity": {
                "is_valid": False,
                "detected_type": document_type,
                "confidence": "high",
                "message": "Invalid document type..."
            }
        }
    
    # PROCEED with extraction for valid documents
    # ... (extraction logic)
    
    return {
        "records": enriched_records,
        "document_validity": {
            "is_valid": True,
            "detected_type": document_type,
            "confidence": "high",
        }
    }
```

### Backend: Type Validation Function (extraction_service.py)

**Location:** `/src/services/extraction_service.py` lines 557-579

```python
def _is_accepted_doc_type(raw_type: str) -> bool:
    """Return True if raw_type matches accepted NHAI document type."""
    
    if not raw_type:
        return False
    
    normalized = raw_type.lower().strip()
    
    # Exact or substring match against all accepted patterns
    if any(pattern in normalized for pattern in _ACCEPTED_DOC_PATTERNS):
        return True
    
    # Token-level check: "pcc document", "loa form", etc.
    tokens = set(normalized.split())
    if tokens & _ACCEPTED_DOC_TOKENS:
        return True
    
    return False
```

**Accepted Patterns** (defined at line ~530):
```python
_ACCEPTED_DOC_PATTERNS = [
    "letter of award",
    "completion certificate",
    "provisional completion certificate",
    "financial closure",
]

_ACCEPTED_DOC_TOKENS = {
    "loa",
    "cc",
    "pcc",
}
```

### API Response Builder (app.py)

**Location:** `/app.py` lines 168-200

```python
@app.post("/extract")
async def extract(
    attributes: str = Form(...),
    files: list[UploadFile] = File(...),
    output_format: str = Form("json"),
):
    # Process all files
    results: list[dict[str, object]] = await asyncio.gather(
        *[_process_single_upload(upload, requested_attributes) 
          for upload in files]
    )
    
    # Merge results and extract document_validity
    all_records: list[dict[str, object]] = []
    document_validity = None
    
    for result in results:
        all_records.extend(result.get("records", []))
        if document_validity is None and "document_validity" in result:
            document_validity = result["document_validity"]
    
    # Build response with document_validity
    response_data = {
        "attributes": requested_attributes,
        "records": all_records,
    }
    if document_validity:
        response_data["document_validity"] = document_validity
    
    return Response(
        content=json.dumps(response_data, indent=2, ensure_ascii=False),
        media_type="application/json",
    )
```

---

## Frontend: Validation Module (app.js)

**Location:** `/static/app.js` lines 60-209

### DocValidity Module - Overview

```javascript
const DocValidity = (() => {
  const FALLBACK_MSG = "Invalid document type...";
  
  const TYPE_LABELS = {
    loa: "Letter of Award (LOA)",
    cc: "Completion Certificate (CC)",
    pcc: "Provisional Completion Certificate (PCC)",
    "financial closure": "Financial Closure",
  };
  
  function evaluate(validity) {
    // Case 1: Hard block (is_valid: false)
    if (!is_valid) {
      // Show amber warning banner
      // Wire button event handlers
      // Return false (suppress results)
    }
    
    // Case 2: Soft notice (is_valid: true + low confidence)
    if (is_valid && confidence === "low") {
      // Show info banner
      // Return true (show results)
    }
    
    // Case 3: High/medium confidence
    return true;  // Show results, no banner
  }
  
  return { evaluate, reset };
})();
```

### Warning Banner HTML (DocValidity.evaluate)

When `is_valid: false`, this banner is injected:

```html
<div class="doc-validity-banner doc-validity-banner--block">
  <div class="banner-header">
    <span class="banner-icon" aria-hidden="true">⚠️</span>
    <div class="banner-header-text">
      <p class="banner-title">
        Invalid Document Type Detected (invoice). Extraction Halted.
      </p>
      <p class="banner-body">
        We couldn't identify this as a Letter of Award (LOA)...
      </p>
    </div>
  </div>
  <div class="banner-actions">
    <button class="banner-action banner-action--primary" id="bannerUploadBtn">
      ↑ Upload Correct Document
    </button>
    <button class="banner-action banner-action--secondary" id="bannerForceExtractBtn">
      Force Extract Anyway
    </button>
  </div>
</div>
```

---

## Frontend: Validation Gate (app.js)

**Location:** `/static/app.js` lines 1162-1195

```javascript
// After extraction completes and response received:

// ── PRE-RENDER HARD GATE: Document Type Validation ────────────────────
const validity = data.document_validity ?? null;
console.log('[DEBUG] Document Validity:', validity);

// Store records globally
allRecords   = records;
currentIndex = 0;

// EVALUATE: Should we render results?
const shouldRenderResults = DocValidity.evaluate(validity);
console.log('[DEBUG] Should Render Results:', shouldRenderResults);

// HARD STOP if validation fails
if (!shouldRenderResults) {
  // ❌ INVALID DOCUMENT DETECTED
  resultForm.hidden = true;      // Hide results
  resetSummaryDashboard();       // Clear summary
  setStatus("ready", "System Operational");
  setMessage("");
  return;  // CRITICAL: Exit function without generating summary
}

// ✅ DOCUMENT VALID - Proceed with results + summary
showResultPanel(records, records[0]?._pdfUrl ?? null);

// NOW generate summary (only for valid documents)
summaryRequestId += 1;
summarizeSelectedFiles(summaryRequestId);
```

---

## CSS: Warning Banner Styling (styles.css)

The banner uses these classes (search in styles.css):

```css
.doc-validity-banner {
  display: none;  /* Hidden by default */
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
}

.doc-validity-banner--block {
  display: block;  /* Show when invalid */
  background: #FFFDF5;
  border: 1px solid #FDE68A;
  border-left: 4px solid #F59E0B;
}

.doc-validity-banner--notice {
  display: block;
  background: #FFFBF0;
  border: 1px solid #FED7AA;
  border-left: 4px solid #F97316;
}

.banner-header {
  display: flex;
  gap: 12px;
  margin-bottom: 8px;
}

.banner-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.banner-title {
  font-weight: 600;
  color: #854D0E;
}

.banner-body {
  color: #A16207;
  font-size: 13px;
}

.banner-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.banner-action {
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
}

.banner-action--primary {
  background: #F59E0B;
  color: white;
  border: none;
}

.banner-action--secondary {
  background: white;
  border: 1px solid #CBD5E1;
  color: #1E293B;
}
```

---

## API Response Example

### Invalid Document Response

```json
{
  "attributes": ["tender_id"],
  "records": [
    {
      "status": "Blocked",
      "reason": "Type: 'invoice' not in accepted types",
      "message": "Blocking extraction and returning validation error"
    }
  ],
  "document_validity": {
    "is_valid": false,
    "detected_type": "invoice",
    "confidence": "high",
    "message": "Invalid document type detected..."
  }
}
```

### Valid Document Response

```json
{
  "attributes": ["tender_id", "location"],
  "records": [
    {
      "tender_id": "NHAI/TEN/2024/001",
      "location": "Maharashtra",
      "_pdfUrl": "blob:http://localhost:8000/..."
    }
  ],
  "document_validity": {
    "is_valid": true,
    "detected_type": "Letter of Award (LOA)",
    "confidence": "high"
  }
}
```

---

## Execution Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ User uploads PDF and clicks "Extract Data"                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ POST /extract          │
        │ (frontend sends PDF)   │
        └────────────┬───────────┘
                     │
        ┌────────────▼───────────────────────────┐
        │ Backend: _process_single_upload()     │
        └────────────┬───────────────────────────┘
                     │
        ┌────────────▼───────────────────────────┐
        │ Backend: classify_document()           │
        │ (Phase 1 Classification)               │
        └────────────┬───────────────────────────┘
                     │
        ┌────────────▼───────────────────────────┐
        │ Backend: _is_accepted_doc_type()      │
        │ (Check if type matches whitelist)      │
        └────────────┬───────────────────────────┘
                     │
              ┌──────┴──────┐
              │             │
          ✅ Valid    ❌ Invalid
              │             │
              │        ┌────▼──────────────────────┐
              │        │ Return early abort        │
              │        │ records: [{ status:... }] │
              │        │ document_validity: {      │
              │        │   is_valid: false, ...    │
              │        │ }                         │
              │        └────┬──────────────────────┘
              │             │
              │        ┌────▼──────────────────────┐
              │        │ Log: PHASE 1 BLOCKED      │
              │        └────┬──────────────────────┘
              │             │
    ┌─────────┴─────────┐   │
    │ Extract data      │   │
    │ Build records     │   │
    │ Set is_valid:true │   │
    └──────────┬────────┘   │
               │            │
               └─────┬──────┘
                     │
        ┌────────────▼─────────────────────┐
        │ Frontend: response received      │
        │ Check: data.document_validity    │
        └────────────┬─────────────────────┘
                     │
        ┌────────────▼─────────────────────────┐
        │ Frontend: DocValidity.evaluate()    │
        └────────────┬─────────────────────────┘
                     │
              ┌──────┴────────┐
              │               │
          ✅ true        ❌ false
          (valid)        (invalid)
              │               │
              │        ┌──────▼──────────────────┐
              │        │ Show warning banner     │
              │        │ Hide results            │
              │        │ Clear summary           │
              │        │ Return from function    │
              │        │ (NO SUMMARY GENERATED)  │
              │        └──────────────────────────┘
              │
        ┌─────▼──────────────────────┐
        │ Show extraction results    │
        │ (resultForm.hidden = false)│
        └─────┬──────────────────────┘
              │
        ┌─────▼──────────────────────┐
        │ Generate summary           │
        │ summarizeSelectedFiles()   │
        └─────┬──────────────────────┘
              │
        ┌─────▼──────────────────────┐
        │ Display summary results    │
        └────────────────────────────┘
```

---

## Key Files Summary

| File | Purpose | Key Functions/Lines |
|------|---------|-------------------|
| `/app.py` | Extract endpoint | Lines 168-200: Merge results + return document_validity |
| `/src/services/extraction_service.py` | Classification & validation | Lines 557-783: Classification, validation check, early abort |
| `/static/app.js` | Frontend validation | Lines 60-209: DocValidity module, Lines 1162-1195: Validation gate |
| `/static/styles.css` | Banner styling | `.doc-validity-banner--block` classes |

---

## Testing Checklist

- [ ] Backend returns `document_validity` in API response
- [ ] Backend shows `PHASE 1 BLOCKED` for invalid docs
- [ ] Backend shows `Classified as: <type>` for valid docs
- [ ] Frontend receives `document_validity` in response
- [ ] Frontend calls `DocValidity.evaluate()` 
- [ ] DocValidity returns `false` for invalid docs
- [ ] Warning banner shows when `is_valid: false`
- [ ] Results hidden when `is_valid: false`
- [ ] Summary NOT generated when `is_valid: false`
- [ ] Results shown when `is_valid: true`
- [ ] Summary generated when `is_valid: true`

---

## Console Debug Output

**For Invalid Document - Expected Console Logs:**

```javascript
[DEBUG] Merging 1 results
[DEBUG] Result 0: Keys = dict_keys(['records', 'document_validity'])
[DEBUG] Set document_validity: {'is_valid': false, 'detected_type': 'invoice', ...}
[DEBUG] Final document_validity: {'is_valid': false, ...}
[DEBUG] Response includes document_validity: {'is_valid': false, ...}
[DEBUG] Full response keys: dict_keys(['attributes', 'records', 'document_validity'])
[DEBUG] API Response validity: {'is_valid': false, 'detected_type': 'invoice', ...}
[DEBUG] is_valid: false
[DEBUG] DocValidity.evaluate() returned: false
[DEBUG] VALIDATION FAILED - Blocking extraction
[DEBUG] Returning early - no summary will be generated
```

**For Valid Document - Expected Console Logs:**

```javascript
[DEBUG] API Response validity: {'is_valid': true, 'detected_type': 'Letter of Award (LOA)', ...}
[DEBUG] is_valid: true
[DEBUG] DocValidity.evaluate() returned: true
[DEBUG] VALIDATION PASSED - Proceeding with extraction
```


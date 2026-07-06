# Document Validation System - Complete Implementation Guide

## ✅ What Has Been Implemented

The document validation system is **fully implemented** across the entire stack:

### Backend (Python/FastAPI)

1. **Pre-Extraction Classification Gate** (`src/services/extraction_service.py`)
   - `classify_document()` method: Quick, lightweight document classification
   - Returns document type: "letter of award (loa)", "completion certificate (cc)", "provisional completion certificate (pcc)", "financial closure", or "other"
   - Takes ~2-3 seconds (uses Gemini API)

2. **Validation Logic** (`_is_accepted_doc_type()` function)
   - ✅ Verified working correctly with all test cases
   - Accepts only the 4 NHAI document types
   - Rejects everything else as "other"

3. **Integration in Extraction Pipeline**
   - Phase 1: Document classification (quick gate)
   - Phase 2: Full extraction (only if Phase 1 passes)
   - Returns `document_validity` object in API response

4. **API Response Structure**
   ```json
   {
     "attributes": [...],
     "records": [...],
     "document_validity": {
       "is_valid": false,
       "detected_type": "invoice",
       "confidence": "high",
       "message": null
     }
   }
   ```

### Frontend (JavaScript/HTML)

1. **DocValidity Module** (`static/app.js`)
   - Evaluates the `document_validity` response
   - Shows/hides warning banner based on validity

2. **Warning Banner** (HTML in `templates/index.html`)
   - Shows when `is_valid: false`
   - Displays detected document type
   - Offers two buttons:
     - "Upload Correct Document" (clears upload and refocuses)
     - "Force Extract Anyway" (dismisses banner and proceeds)

3. **Hard Gate Logic**
   - If invalid: Results hidden, summary not generated
   - If valid: Results shown, summary generated

### New Testing Tool

- New endpoint: `/test-validation` - Opens an interactive testing dashboard
- URL: http://localhost:8000/test-validation
- Features:
  - Test classification endpoint with any PDF
  - Test full extraction endpoint
  - Run automated diagnostics
  - See exact API responses

## 🔍 How to Verify It's Working

### Step 1: Restart Everything (Fresh Start)

```bash
# Kill the server
pkill -f "uvicorn app:app"

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +

# Clear browser cache (do this in browser)
# Mac: Cmd+Shift+Delete or Settings → Clear browsing data
# Windows: Ctrl+Shift+Delete

# Restart server
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload --log-level debug
```

### Step 2: Use the Testing Tool

1. Open http://localhost:8000/test-validation
2. Upload a NON-NHAI PDF (invoice, ACR form, etc.)
3. Click "Test Classification"
4. Expected result:
   ```json
   {
     "classified_as": "invoice",
     "is_valid": false,
     "message": "Classification successful"
   }
```

### Step 3: Watch Server Logs

When classification runs, you should see in the server terminal:

```
======================================================================
PHASE 1 START: Classifying document: filename.pdf
======================================================================

>>> Phase 1 Classification Result <<<
  Document Type: 'invoice'
  Is Valid: False
  ...

======================================================================
PHASE 1 BLOCKED: Document rejected
  Type: 'invoice' not in accepted types
  Blocking extraction and returning validation error
======================================================================
```

### Step 4: Test Full Extraction

1. Go back to http://localhost:8000
2. Upload a non-NHAI PDF
3. Enter an attribute (e.g., "project_name")
4. Click "Extract Data"
5. After ~2-3 seconds, you should see:
   - ⚠️ Amber warning banner appears
   - No extraction results shown
   - No summary generated
   - Two buttons: "Upload Correct Document" and "Force Extract Anyway"

### Step 5: Check Browser DevTools

Open Browser DevTools (F12) and go to Console tab:

```javascript
[DEBUG] API Response: { attributes: [...], records: [...], document_validity: {...} }
[DEBUG] Document Validity: { is_valid: false, detected_type: 'invoice', ... }
[DEBUG] Should Render Results: false
```

If you see these logs, the frontend is working correctly.

## 🐛 Troubleshooting

### Issue: Warning banner not showing for invalid documents

**Check List:**
1. [ ] Server restarted? (look for "Application startup complete" in logs)
2. [ ] Browser cache cleared? (Hard refresh: Cmd+Shift+R on Mac, Ctrl+F5 on Windows)
3. [ ] Console logs showing `[DEBUG] Document Validity:`? (F12 → Console)
4. [ ] API response has `document_validity` key? (F12 → Network → /extract → Response)

**Diagnostic Command:**
```bash
curl -X POST http://localhost:8000/test-classify \
  -F "file=@/path/to/your/invoice.pdf"
```

Expected output:
```json
{"classified_as":"invoice","is_valid":false,"message":"Classification successful"}
```

### Issue: Summary still generating for invalid documents

This should NOT happen if the validation gate is working.

**Check:**
- [ ] Is `classify_document()` returning the correct type? (Check `/test-validate` tool)
- [ ] Is the API response including `document_validity`? (Check Network tab in DevTools)
- [ ] Is the frontend evaluating validity BEFORE generating summary? (Check Console logs)

### Issue: Extraction still happening for invalid documents

**Check:**
- [ ] Extract Phase 1 logs appear in server terminal?
- [ ] Is it showing "PHASE 1 BLOCKED" or proceeding to "PHASE 2"?
- [ ] Do your records have `"status": "Blocked"`?

## 📊 Testing with Different Document Types

### Valid Documents (should proceed)
- Letter of Award (LOA)
- Completion Certificate (CC)
- Provisional Completion Certificate (PCC)
- Financial Closure

### Invalid Documents (should show warning)
- Invoice
- Purchase Order
- ACR Form
- Any non-NHAI document

## 🔧 Configuration

### Accepted Document Types

Located in `src/services/extraction_service.py`:

```python
_ACCEPTED_DOC_PATTERNS: list[str] = [
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
    "letter of award",
    "financial closure",
    "provisional completion certificate",
    "provisional completion",
    "completion certificate",
    "provisional cc",
    "provisional pcc",
]

_ACCEPTED_DOC_TOKENS: frozenset[str] = frozenset(["loa", "cc", "pcc"])
```

To add or change accepted types, modify these lists.

## 📝 Next Steps

If the system is working correctly:
1. ✅ Invalid documents show warning banner
2. ✅ Valid documents proceed with extraction
3. ✅ "Force Extract Anyway" button allows override
4. ✅ Summary only generates for valid documents or after override

If issues persist:
1. Run the `/test-validation` tool to identify which component is failing
2. Check server logs (run with `--log-level debug`)
3. Check browser DevTools Console tab
4. Check Network tab to see exact API responses

## 🚀 Production Deployment

When deploying to production:

1. Update the Gemini classification prompt if needed (in `classify_document()`)
2. Adjust confidence level if needed (currently "high" for both valid and invalid)
3. Consider caching classification results to save API costs
4. Add monitoring to track classification accuracy
5. Set up alerts for unexpected rejection patterns

---

**Last Updated:** After backend refactor with Phase 1 validation gate
**Status:** ✅ Fully Implemented and Ready for Testing

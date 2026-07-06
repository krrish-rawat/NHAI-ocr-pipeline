# ⚡ QUICK START: Verify Document Validation Is Working

**Total time: ~5 minutes**

## Prerequisites

- Server running: `uvicorn app:app --reload`
- Browser open to http://localhost:8000
- Test PDF ready (invoice, ACR form, or any non-NHAI document)

---

## TEST 1: Server Health Check

**Goal:** Verify server restarted with new code

```bash
# In terminal
curl http://localhost:8000/test-validation

# Expected: Should return HTML page (not an error)
```

---

## TEST 2: Classification Endpoint

**Goal:** Verify document classification is working

```bash
# In terminal, replace path with your test PDF
curl -X POST http://localhost:8000/test-classify \
  -F "file=@/path/to/invoice.pdf"
```

**Expected output for invalid document:**
```json
{
  "classified_as": "invoice",
  "is_valid": false,
  "message": "Classification successful"
}
```

**What this tells you:**
- ✅ Classification endpoint is working
- ✅ Gemini API is responding
- ✅ Document type detection is correct

---

## TEST 3: Full Extraction Pipeline

**Goal:** Test the complete validation gate

### Via Browser UI:

1. Open http://localhost:8000 in browser
2. Upload a non-NHAI PDF (invoice, ACR form, etc.)
3. Enter an attribute: `project_name`
4. Click "Extract Data"
5. Wait 2-3 seconds

**Expected behavior:**
- Progress bar appears and progresses to ~30%
- Progress bar disappears
- ⚠️ **Amber warning banner appears** with:
  - Icon: ⚠️
  - Title: "Invalid Document Type Detected (invoice). Extraction Halted."
  - Message: "We only accept: Letter of Award (LOA), Completion Certificate (CC), Provisional CC, or Financial Closure documents."
  - Buttons: "Upload Correct Document" and "Force Extract Anyway"
- ❌ No extraction results shown
- ❌ No summary generated

### Via cURL (to verify API response):

```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@/path/to/invoice.pdf" \
  -F "attributes=project_name" \
  -F "output_format=json" | python3 -m json.tool | head -50
```

**Expected JSON response:**
```json
{
  "attributes": ["project_name"],
  "records": [
    {
      "source_file": "invoice.pdf",
      "project_name": "Null",
      "status": "Blocked",
      "failure_reason": "Invalid document type: invoice"
    }
  ],
  "document_validity": {
    "is_valid": false,
    "detected_type": "invoice",
    "confidence": "high",
    "message": null
  }
}
```

**Critical checks:**
- ✅ `document_validity` key exists
- ✅ `is_valid` is `false`
- ✅ `detected_type` matches actual document type
- ✅ `records[0].status` is `"Blocked"`

---

## TEST 4: Browser DevTools Verification

**Goal:** Verify frontend is reading validation response

1. Open http://localhost:8000
2. Press **F12** to open DevTools
3. Go to **Console** tab
4. Upload an invalid PDF and click "Extract Data"
5. Watch the console output

**Expected logs:**
```
[DEBUG] API Response: {attributes: Array(1), records: Array(1), document_validity: {...}}
[DEBUG] Document Validity: {is_valid: false, detected_type: "invoice", confidence: "high", message: null}
[DEBUG] Should Render Results: false
```

**If you don't see these logs:**
- Click **Network** tab
- Find the `/extract` request
- Click on it
- Go to **Response** tab
- Look for `"document_validity"` in the JSON

If it's not there, the backend is not returning it.

---

## TEST 5: Server Logs Verification

**Goal:** Verify Phase 1 classification is running in backend

1. Look at the server terminal where uvicorn is running
2. Upload a non-NHAI PDF and click "Extract Data"
3. Watch for these logs:

**Expected output:**
```
======================================================================
PHASE 1 START: Classifying document: invoice.pdf
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

**If you see "PHASE 2 START" instead of "PHASE 1 BLOCKED":**
- This means classification returned an accepted type
- Check the `Document Type` value
- If it says "loa", "cc", "pcc", or "financial closure" - this is why extraction proceeded

---

## TEST 6: "Force Extract Anyway" Button

**Goal:** Verify override functionality works

1. Follow TEST 3 to get the warning banner
2. Click the "Force Extract Anyway" button
3. Wait 2-3 seconds

**Expected behavior:**
- Banner disappears
- Extraction results appear
- Summary generates
- Button becomes "✓ Done" (green)

---

## TEST 7: Valid Document (Control Test)

**Goal:** Verify system works correctly for valid documents

1. Get a real Letter of Award (LOA) or Completion Certificate PDF
2. Upload it to http://localhost:8000
3. Enter attributes
4. Click "Extract Data"

**Expected behavior:**
- ⚠️ No warning banner appears
- ✅ Extraction results appear (if API works)
- ✅ Summary generates (if summarization works)
- ✅ Button becomes "✓ Done"

---

## 🆘 If Something Doesn't Work

### Warning Banner Not Showing for Invalid Documents

**Step 1: Check API Response**
```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@/path/to/invalid_doc.pdf" \
  -F "attributes=project_name" \
  -F "output_format=json" | grep document_validity
```

**If output is empty:**
- Backend is not returning `document_validity` 
- Server needs to be restarted
- Check `/Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser/VALIDATION_SYSTEM_GUIDE.md`

**Step 2: Check Browser Console**
- F12 → Console tab
- Upload document
- Look for any red error messages
- If no `[DEBUG]` logs appear, JavaScript isn't running

**Step 3: Check Server Logs**
- Look for "PHASE 1 START" message
- If not there, `classify_document()` isn't being called
- Check if server reloaded (look for "application startup complete")

### Extraction Still Happens for Invalid Documents

**Step 1: Verify Classification**
```bash
curl -X POST http://localhost:8000/test-classify \
  -F "file=@/path/to/your_document.pdf"
```

If `"is_valid": true`, the document is being classified as an accepted type.

**Step 2: Check Detected Type**
- What is the actual document you're testing?
- Is it possible it looks like an LOA/CC/PCC to the LLM?
- Try with a different document

**Step 3: Check Server Logs**
- Is it showing "PHASE 1 BLOCKED" or "PHASE 2 START"?
- If PHASE 2, that means classification returned an accepted type

---

## Quick Restart Commands

If things aren't working:

```bash
# Kill server
pkill -f "uvicorn app:app"

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +

# Clear browser cache (in browser):
# Mac: Cmd+Shift+Delete
# Windows: Ctrl+Shift+Delete

# Restart server
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload --log-level debug
```

---

## Summary

✅ **If you see all of this:**
1. Warning banner appears for invalid documents
2. `[DEBUG]` logs in browser console
3. "PHASE 1 BLOCKED" in server logs
4. API response includes `document_validity`

**Then the system is working correctly!**

---

**Next: Share which test fails and what you see in the console/logs**

# 🔧 Warning Banner Not Showing - Troubleshooting Guide

## Quick Check

**Did you restart the server after making changes?**

```bash
# Stop the server (Ctrl+C)
# Then restart:
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload
```

**Hard refresh the browser:**
- **Mac:** Cmd + Shift + R
- **Windows:** Ctrl + F5

## Use the Test Tool

I've created a comprehensive test tool:

```bash
# 1. Start the server
uvicorn app:app --reload

# 2. Open in browser:
http://localhost:8000/test_warning_banner.html
```

This tool will test:
1. ✅ Backend classification working
2. ✅ Full extraction returning `document_validity`
3. ✅ Frontend `DocValidity.evaluate()` logic
4. ✅ Banner element exists in DOM

**Follow the tests in order** - they'll tell you exactly where the problem is.

## Manual Debug Steps

### Step 1: Check Backend Classification

```bash
# Test with any PDF file
curl -X POST http://localhost:8000/test-classify \
  -F "file=@/path/to/your/test.pdf"
```

**Expected for invalid document:**
```json
{
  "classified_as": "invoice",
  "is_valid": false,
  "message": "Classification successful"
}
```

**If you get an error:** Check Gemini API key in `.env`

### Step 2: Check Full Extraction Response

```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@/path/to/your/test.pdf" \
  -F "attributes=test_field" \
  -F "output_format=json" | python3 -m json.tool | grep -A 5 "document_validity"
```

**Expected:**
```json
"document_validity": {
  "is_valid": false,
  "detected_type": "invoice",
  "confidence": "high",
  "message": null
}
```

**If `document_validity` is missing:**
- Server wasn't restarted
- Check server terminal for Python errors

### Step 3: Check Browser Console

1. Open http://localhost:8000
2. Press F12 (open DevTools)
3. Go to Console tab
4. Upload a PDF and click "Extract Data"

**Look for these logs:**
```
[DEBUG] API Response: {attributes: [...], document_validity: {...}}
[DEBUG] Document Validity: {is_valid: false, detected_type: "invoice"}
[DEBUG] Should Render Results: false
```

**If you DON'T see these logs:**
- The JavaScript wasn't reloaded
- Hard refresh: Cmd+Shift+R (Mac) or Ctrl+F5 (Windows)

### Step 4: Check Banner Element

In browser console, type:

```javascript
document.querySelector('#docValidityBanner')
```

**Expected:** Returns a div element
**If null:** Banner element missing from HTML

### Step 5: Manually Test DocValidity

In browser console on http://localhost:8000:

```javascript
const testData = {
  is_valid: false,
  detected_type: "Invoice",
  confidence: "high",
  message: null
};

const result = DocValidity.evaluate(testData);
console.log('Result:', result);  // Should be false
console.log('Banner hidden?', docValidityBanner.hidden);  // Should be false (visible)
```

## Common Problems & Solutions

### Problem: "Classification returns 'other' for everything"

**Cause:** Gemini can't read the PDF properly

**Solution:**
1. Check PDF isn't corrupted
2. Try a different PDF
3. Check server logs for PyMuPDF errors

### Problem: "`document_validity` always `null`"

**Cause:** Backend code not updated

**Solution:**
```bash
# 1. Verify changes are in place
grep -n "def classify_document" src/services/extraction_service.py

# 2. Restart server
uvicorn app:app --reload
```

### Problem: "Console shows `is_valid: false` but banner doesn't appear"

**Cause:** `DocValidity.evaluate()` not working

**Solution:** Check in browser console:
```javascript
// Test if DocValidity exists
typeof DocValidity

// Check banner element
document.querySelector('#docValidityBanner')

// Manually trigger
DocValidity.evaluate({is_valid: false, detected_type: "test"})
```

### Problem: "Server logs don't show 'Phase 1: Classifying document'"

**Cause:** `classify_document()` not being called

**Solution:**
1. Check `extract_file_records()` has Phase 1 code
2. Restart server
3. Check for Python syntax errors in terminal

## Verification Checklist

Run these commands to verify everything is in place:

```bash
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser

# 1. Check classify_document method exists
echo "1. classify_document:"
grep -q "def classify_document" src/services/extraction_service.py && echo "✓" || echo "✗"

# 2. Check Phase 1 logic exists
echo "2. Phase 1 logic:"
grep -q "PHASE 1" src/services/extraction_service.py && echo "✓" || echo "✗"

# 3. Check frontend debug logs
echo "3. Frontend debug:"
grep -q "DEBUG.*Document Validity" static/app.js && echo "✓" || echo "✗"

# 4. Check test endpoint
echo "4. Test endpoint:"
grep -q "test-classify" app.py && echo "✓" || echo "✗"

# 5. Check API key
echo "5. API key:"
grep -q "GEMINI_API_KEY\|GOOGLE_API_KEY" .env && echo "✓" || echo "✗"
```

All should show `✓`.

## Still Not Working?

### Get Server Logs

```bash
# Run server with verbose output
uvicorn app:app --reload --log-level debug
```

Look for:
- `Phase 1: Classifying document: ...`
- `Classification result: '...' | Valid: ...`
- Any Python exceptions or tracebacks

### Check Network Tab

1. F12 → Network tab
2. Upload PDF and extract
3. Find `/extract` request
4. Click → Response tab
5. Look for `document_validity` in JSON

### Enable More Logging

Add to `src/services/extraction_service.py` at the top of `extract_file_records`:

```python
def extract_file_records(...):
    logger.info(f"=" * 70)
    logger.info(f"EXTRACT FILE RECORDS CALLED: {source_file}")
    logger.info(f"=" * 70)
    # ... rest of method
```

This will show in server logs if the method is even being called.

## Contact Info

If still stuck after trying all steps:

1. ✅ Run the test tool: http://localhost:8000/test_warning_banner.html
2. ✅ Note which specific test fails
3. ✅ Copy the error message
4. ✅ Check server logs for errors
5. ✅ Share the specific failing test + error message

---

**Most common issue:** Server wasn't restarted or browser cache not cleared. Always try those first! 🔄

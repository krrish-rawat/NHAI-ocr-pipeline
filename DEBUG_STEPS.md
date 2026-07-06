# Debugging Steps - Why Warning Not Showing

## Step 1: Check if Server is Running with Latest Code

```bash
# Stop any running server (Ctrl+C)
# Then restart:
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload
```

Look for: `Application startup complete.`

## Step 2: Test Classification Endpoint Directly

Open a new terminal and test the classification:

```bash
# Replace 'your_test_file.pdf' with an actual PDF
curl -X POST http://localhost:8000/test-classify \
  -F "file=@your_test_file.pdf"
```

**Expected output for INVALID document:**
```json
{
  "classified_as": "invoice",
  "is_valid": false,
  "message": "Classification successful"
}
```

**Expected output for VALID document (LOA):**
```json
{
  "classified_as": "letter of award (loa)",
  "is_valid": true,
  "message": "Classification successful"
}
```

### If you get an error:
- Check Gemini API key in `.env` file
- Look at server terminal for error messages

## Step 3: Test Full Extraction Endpoint

```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@your_test_file.pdf" \
  -F "attributes=field1,field2" \
  -F "output_format=json" | jq '.document_validity'
```

**Expected for INVALID document:**
```json
{
  "is_valid": false,
  "detected_type": "invoice",
  "confidence": "high",
  "message": null
}
```

### If `document_validity` is missing or null:
- The backend classification failed
- Check server logs for Python errors

## Step 4: Test in Browser with Console Open

1. **Open browser to:** http://localhost:8000
2. **Open DevTools:** Press F12 or right-click → Inspect
3. **Go to Console tab**
4. **Upload a test PDF**
5. **Click "Extract Data"**

### Look for these console logs:

```
[DEBUG] API Response: {attributes: [...], records: [...], document_validity: {...}}
[DEBUG] Document Validity: {is_valid: false, detected_type: "invoice", ...}
[DEBUG] Should Render Results: false
```

### What each log tells you:

**If you DON'T see `[DEBUG] API Response:`**
- The API call failed
- Check Network tab for the /extract request
- Look for error status codes (400, 500, etc.)

**If `document_validity` is null or undefined:**
- Backend isn't returning it
- Check server terminal for Python errors
- Verify you restarted the server after code changes

**If `is_valid` is `true` when it should be `false`:**
- Classification is wrong
- Test with Step 2 to verify classification logic
- Check what `detected_type` value is being returned

**If `shouldRenderResults` is `true` when it should be `false`:**
- DocValidity.evaluate() isn't working
- Check for JavaScript errors in console
- Verify `docValidityBanner` element exists in DOM

## Step 5: Check Banner Element Exists

In browser console, run:

```javascript
document.querySelector('#docValidityBanner')
```

**Expected:** Should return the banner element
**If null:** The HTML template is missing the banner element

## Step 6: Manually Test DocValidity

In browser console, run:

```javascript
// Test with invalid document
const testValidity = {
  is_valid: false,
  detected_type: "Invoice",
  confidence: "high",
  message: null
};

const result = DocValidity.evaluate(testValidity);
console.log('Evaluation result:', result);
console.log('Banner hidden?', docValidityBanner.hidden);
```

**Expected:**
- `result` should be `false`
- `docValidityBanner.hidden` should be `false` (banner is visible)

## Step 7: Check Server Logs

Look at the server terminal for these logs:

```
Phase 1: Classifying document: test.pdf
Classification result: 'invoice' | Valid: False
Document rejected: 'invoice' not in accepted types
```

### If you DON'T see these logs:
- `classify_document()` isn't being called
- Check that you saved and restarted the server
- Verify the code changes are in place

## Step 8: Verify Code Changes

Check key files:

```bash
# 1. Check classify_document exists
grep -A 5 "def classify_document" src/services/extraction_service.py

# 2. Check extract_file_records calls it
grep -A 10 "PHASE 1" src/services/extraction_service.py

# 3. Check frontend debug logs
grep "DEBUG" static/app.js
```

## Common Issues & Solutions

### Issue: "Banner never appears"

**Possible causes:**
1. ✅ Server not restarted → Restart with `uvicorn app:app --reload`
2. ✅ `document_validity` not in API response → Check Step 3
3. ✅ `DocValidity.evaluate()` not called → Check Step 4 console logs
4. ✅ Banner element missing → Check Step 5
5. ✅ CSS hiding banner → Check browser DevTools → Elements tab

### Issue: "Extraction still runs for invalid docs"

**Possible causes:**
1. ✅ Classification failing → Check Step 2
2. ✅ `_is_accepted_doc_type()` always returning True → Test with Step 2
3. ✅ Early abort not reached → Check server logs (Step 7)

### Issue: "Summary still generates for invalid docs"

**Possible causes:**
1. ✅ Frontend validation check failing → Check Step 4 console logs
2. ✅ `shouldRenderResults` is True → Check Step 4
3. ✅ Summary call before validation → Check that code changes are in static/app.js

## Quick Diagnostic Command

Run this all-in-one check:

```bash
# Check if all changes are in place
echo "=== Checking classify_document ===" && \
grep -q "def classify_document" src/services/extraction_service.py && echo "✓ Found" || echo "✗ Missing"

echo "=== Checking PHASE 1 ===" && \
grep -q "PHASE 1" src/services/extraction_service.py && echo "✓ Found" || echo "✗ Missing"

echo "=== Checking frontend DEBUG ===" && \
grep -q "DEBUG.*Document Validity" static/app.js && echo "✓ Found" || echo "✗ Missing"

echo "=== Checking test endpoint ===" && \
grep -q "test-classify" app.py && echo "✓ Found" || echo "✗ Missing"
```

All should show `✓ Found`.

---

**Start with Step 1 and Step 2 first - these will tell you if classification is working at all.**

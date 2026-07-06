# Complete End-to-End Test Flow

## ✅ All Code Is In Place

The system has been fully implemented:

1. ✅ Backend Phase 1 Classification
2. ✅ Backend document_validity object generation
3. ✅ Backend validation gate that blocks invalid docs
4. ✅ Frontend DocValidity module
5. ✅ Frontend validation check before rendering results
6. ✅ Frontend warning banner with action buttons
7. ✅ Frontend summary suppression for invalid docs

## 🧪 Test Scenario 1: Invalid Document (Should Block)

### Prerequisites
- [ ] Browser hard-refreshed (`Cmd+Shift+R` on Mac)
- [ ] Server running (`uvicorn app:app --reload`)
- [ ] DevTools open (`F12`)
- [ ] Console tab visible

### Test Steps

1. **Upload invalid PDF**
   - Find a PDF that is NOT: LOA, CC, PCC, or Financial Closure
   - Examples: Invoice, ACR Form, Receipt, generic report
   - Drag or click to upload

2. **Enter attribute and extract**
   - Type any attribute (e.g., "tender_id", "test")
   - Click "Extract Data"
   - Start timer

3. **Monitor console (2-3 seconds)**
   - Watch for this sequence in console:
   ```
   [DEBUG] Merging 1 results
   [DEBUG] Result 0: Keys = dict_keys(['records', 'document_validity'])
   [DEBUG] Set document_validity: {'is_valid': False, 'detected_type': '...', ...}
   [DEBUG] Final document_validity: {'is_valid': False, ...}
   [DEBUG] Response includes document_validity: {'is_valid': False, ...}
   [DEBUG] Full response keys: dict_keys(['attributes', 'records', 'document_validity'])
   [DEBUG] API Response validity: {'is_valid': False, ...}
   [DEBUG] is_valid: false
   [DEBUG] DocValidity.evaluate() returned: false
   [DEBUG] VALIDATION FAILED - Blocking extraction
   [DEBUG] Returning early - no summary will be generated
   ```

4. **Verify UI state**
   - ⚠️ Amber warning banner appears
   - ❌ Result panel is HIDDEN
   - ❌ Summary section is EMPTY
   - 🔘 Two buttons visible: "Upload Correct Document" + "Force Extract Anyway"

5. **Test button actions**
   - Click "Upload Correct Document" → File picker opens
   - Click "Force Extract Anyway" → Banner disappears, results show, summary generates

**Expected Result:** ✅ PASS - Invalid document blocked, banner shown, summary NOT generated

---

## 🧪 Test Scenario 2: Valid Document (Should Proceed)

### Prerequisites
- [ ] Same as above
- [ ] Valid NHAI document ready (LOA, CC, PCC, or Financial Closure)

### Test Steps

1. **Upload valid PDF**
   - Upload an LOA, Completion Certificate, PCC, or Financial Closure document
   - Drag or click to upload

2. **Enter attributes and extract**
   - Type attributes you want to extract
   - Click "Extract Data"
   - Start timer (25-30 seconds)

3. **Monitor console**
   - Should see:
   ```
   [DEBUG] API Response validity: {'is_valid': True, 'detected_type': 'Letter of Award (LOA)', ...}
   [DEBUG] is_valid: true
   [DEBUG] DocValidity.evaluate() returned: true
   [DEBUG] VALIDATION PASSED - Proceeding with extraction
   ```
   - NO "VALIDATION FAILED" message

4. **Verify UI state**
   - ✅ NO warning banner
   - ✅ Result panel is VISIBLE (shows extracted data)
   - ✅ Summary section generates and populates (after ~25 seconds)
   - ✅ Status shows "Extraction Complete"

**Expected Result:** ✅ PASS - Valid document processed, results shown, summary generated

---

## 🔍 Debug Checklist If Tests Fail

### Debug 1: No Console Logs At All

**Issue:** Console shows no `[DEBUG]` messages

**Fixes (in order):**
1. [ ] Browser not hard-refreshed → Do `Cmd+Shift+R` (Mac) or `Ctrl+F5` (Windows)
2. [ ] Cache not cleared → Open DevTools → Application → Storage → Clear all
3. [ ] JavaScript error → Look for RED errors in console
4. [ ] Server not serving new code → Restart: `pkill -f uvicorn && uvicorn app:app --reload`

### Debug 2: Console Shows "VALIDATION PASSED" for Invalid Document

**Issue:** `is_valid: false` in backend, but evaluate() returns true

**Root Cause:** DocValidity.evaluate() function has a bug

**Fix:** Check `/static/app.js` line 114-120:
```javascript
if (!is_valid) {
  // ... show banner ...
  return false;   // Must be here!
}
```

**Verify:** Copy-paste this in console:
```javascript
const testValidity = {is_valid: false, detected_type: "test"};
console.log("evaluate returned:", DocValidity.evaluate(testValidity));
// Should log: evaluate returned: false
```

### Debug 3: Results Still Show Despite "VALIDATION FAILED" Message

**Issue:** Console shows validation failed, but results still visible

**Root Cause:** `showResultPanel()` is being called somewhere else

**Fix:** Check `/static/app.js`:
- Search for all calls to `showResultPanel()`
- Ensure none happen after validation returns false
- Verify `resultForm.hidden = true` is being executed

### Debug 4: Banner Shows But Summary Still Generates

**Issue:** Warning banner visible, but summary is generating

**Root Cause:** Summary request started before validation check

**Fix:** Check `/static/app.js` line 1195:
```javascript
// Must be AFTER validation check, inside the "if (shouldRenderResults)" block
summaryRequestId += 1;
summarizeSelectedFiles(summaryRequestId);
```

### Debug 5: Backend Not Returning document_validity

**Issue:** API response has `records` but no `document_validity` key

**Test:** Run in terminal:
```bash
curl -X POST http://localhost:8000/extract \
  -F "files=@/path/to/test.pdf" \
  -F "attributes=test" \
  -F "output_format=json" 2>/dev/null | python3 -m json.tool | head -50
```

**Expected:** Response includes:
```json
{
  "attributes": [...],
  "records": [...],
  "document_validity": {
    "is_valid": false/true,
    "detected_type": "...",
    "confidence": "high"
  }
}
```

**If Missing:** Check `/app.py` lines 188-192:
```python
if document_validity:
    response_data["document_validity"] = document_validity
```

---

## 📋 Verification Checklist

- [ ] Backend shows `PHASE 1 BLOCKED` for invalid docs
- [ ] Backend shows `Classified as: <type>` for all docs
- [ ] API returns `document_validity` in JSON response
- [ ] Browser hard-refreshed (no old cache)
- [ ] Console shows `[DEBUG]` logs during extraction
- [ ] Invalid doc → validation failed → no results
- [ ] Valid doc → validation passed → results shown
- [ ] Invalid doc → "Force Extract Anyway" → results shown
- [ ] Summary only generates for valid docs or after force extract

---

## 🎯 Expected Console Output For Invalid Doc

```
[DEBUG] Merging 1 results
[DEBUG] Result 0: Keys = dict_keys(['records', 'document_validity'])
[DEBUG] Set document_validity: {'is_valid': False, 'detected_type': 'invoice', 'confidence': 'high', 'message': "..."}
[DEBUG] Final document_validity: {'is_valid': False, 'detected_type': 'invoice', 'confidence': 'high', 'message': "..."}
[DEBUG] Response includes document_validity: {'is_valid': False, 'detected_type': 'invoice', 'confidence': 'high', 'message': "..."}
[DEBUG] Full response keys: dict_keys(['attributes', 'records', 'document_validity'])
[DEBUG] API Response validity: {'is_valid': False, 'detected_type': 'invoice', 'confidence': 'high', 'message': "..."}
[DEBUG] is_valid: false
[DEBUG] DocValidity.evaluate() returned: false
[DEBUG] VALIDATION FAILED - Blocking extraction
[DEBUG] Returning early - no summary will be generated
```

---

## 🚀 Next Steps

1. **Hard refresh browser** → `Cmd+Shift+R` (Mac) or `Ctrl+F5` (Windows)
2. **Run Test Scenario 1** → Invalid document
3. **Copy console output** and share if it doesn't match expected
4. **Run Test Scenario 2** → Valid document
5. **Report any failures** with exact console logs


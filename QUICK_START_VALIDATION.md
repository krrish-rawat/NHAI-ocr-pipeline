# Quick Start: Validation System Test

## One-Command Setup

```bash
# Make sure server is running
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload
```

## One-Step Fix

**Hard refresh browser:** `Cmd+Shift+R` (Mac) or `Ctrl+F5` (Windows)

## Two-Minute Test

1. Hard refresh browser with `Cmd+Shift+R` (Mac) or `Ctrl+F5` (Windows)
2. Open DevTools: Press `F12`
3. Go to **Console** tab
4. Upload an invalid PDF (invoice, ACR form, etc.)
5. Click "Extract Data"
6. **You should see:**
   - Amber warning banner appears
   - NO extraction results
   - NO summary
   - Console shows `[DEBUG] VALIDATION FAILED`

## ✅ What Should Happen

### Invalid Document (e.g., Invoice)
- ⚠️ Amber warning banner
- ❌ No extraction results
- ❌ No summary
- Browser console:
  ```
  [DEBUG] is_valid: false
  [DEBUG] DocValidity.evaluate() returned: false
  [DEBUG] VALIDATION FAILED - Blocking extraction
  ```

### Valid Document (e.g., LOA)
- ✅ No warning banner
- ✅ Extraction results appear
- ✅ Summary generates (25-30 seconds)
- Browser console:
  ```
  [DEBUG] is_valid: true
  [DEBUG] DocValidity.evaluate() returned: true
  [DEBUG] VALIDATION PASSED - Proceeding with extraction
  ```

## 🔍 If It's Not Working

### Step 1: Check Browser Cache
```
Cmd+Shift+R (Mac) or Ctrl+F5 (Windows)
```

### Step 2: Check Server Running
```bash
curl http://localhost:8000
# Should see HTML response, not connection error
```

### Step 3: Test API Directly
```bash
# Test with any PDF file you have
curl -X POST http://localhost:8000/extract \
  -F "files=@/path/to/any.pdf" \
  -F "attributes=test" | python3 -m json.tool | grep -A 3 "document_validity"

# Should see:
# "document_validity": {
#   "is_valid": false or true,
```

### Step 4: Check Console Logs
- Open DevTools (`F12`)
- Go to **Console** tab
- Look for RED errors
- If red errors exist → fix them and restart server
- If no red errors → check if `[DEBUG]` logs appear during extraction

## Files That Control This

| File | What It Does |
|------|-------------|
| `/app.py` | Returns `document_validity` in API response |
| `/src/services/extraction_service.py` | Classifies documents and builds validity object |
| `/static/app.js` | Checks validity and blocks invalid docs |

## Expected API Response

```json
{
  "attributes": ["tender_id"],
  "records": [...],
  "document_validity": {
    "is_valid": false,
    "detected_type": "invoice",
    "confidence": "high",
    "message": "..."
  }
}
```

## Is It Working?

Run this quick test:

```bash
# 1. Stop current server
pkill -f uvicorn

# 2. Start fresh
cd /Users/krrishrawat/Desktop/NHAI-K/Nhai-pdf-parser
uvicorn app:app --reload

# 3. In browser: Cmd+Shift+R (hard refresh)

# 4. Upload invalid doc and watch console
# You should see: [DEBUG] VALIDATION FAILED
```

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| Still seeing extraction for invalid docs | Hard refresh: `Cmd+Shift+R` |
| No `[DEBUG]` logs in console | Cache not cleared; try full browser restart |
| API doesn't return `document_validity` | Restart server |
| Warning banner shows but summary still generates | Clear browser cache and hard refresh |
| Results show for invalid docs even with banner | Check browser console for red errors |

---

**🎯 Main Point:** The system is fully implemented. You just need to hard refresh your browser cache to load the new JavaScript code. After that, everything should work!


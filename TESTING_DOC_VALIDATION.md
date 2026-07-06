# Document Type Validation Testing Guide

## ✅ What Was Implemented

### Frontend Changes (`static/app.js`)

1. **Updated whitelist** to match your requirements:
   - Letter of Award (LOA)
   - Completion Certificate (CC)
   - Provisional Completion Certificate (PCC)
   - Financial Closure

2. **Added pre-render hard gate** that:
   - Evaluates `document_validity` from API response
   - **BLOCKS results rendering** if document type is invalid
   - Shows amber warning banner with two options
   - Stores records globally for force-continue functionality

3. **Enhanced warning banner** with:
   - **"Upload Correct Document"** button (primary, amber)
   - **"Force Extract Anyway"** button (secondary, white)
   - Shows detected document type in title
   - Matches your existing cream/amber UI design

### CSS Changes (`static/styles.css`)

1. Added `.banner-actions` container for button row
2. Added `.banner-action--primary` (amber) and `.banner-action--secondary` (white) button styles
3. Both buttons have hover states and proper focus indicators

## 🧪 Testing Without Backend Changes

To test immediately, you can mock the API response. Add this temporarily to `app.js` after line 1120 (after `const data = await response.json();`):

```javascript
// TEMPORARY: Mock document_validity for testing
data.document_validity = {
  is_valid: false,
  detected_type: "Invoice",  // Try: "loa", "cc", "Invoice", null
  confidence: "high",
  message: null  // Uses default message
};
```

### Test Cases

**Test 1: Valid document (LOA)**
```javascript
data.document_validity = {
  is_valid: true,
  detected_type: "loa",
  confidence: "high"
};
```
Expected: No banner, results render normally

**Test 2: Invalid document**
```javascript
data.document_validity = {
  is_valid: false,
  detected_type: "Invoice",
  confidence: "high"
};
```
Expected: 
- Amber warning banner appears
- Results panel hidden
- Two buttons: "Upload Correct Document" and "Force Extract Anyway"
- Click "Upload Correct Document" → clears upload, opens file picker
- Click "Force Extract Anyway" → banner disappears, results render

**Test 3: Low confidence (shows info banner)**
```javascript
data.document_validity = {
  is_valid: true,
  detected_type: "cc",
  confidence: "low"
};
```
Expected: Blue info banner, results still render

## 🔧 Backend Integration Required

The backend needs to return `document_validity` in the `/extract` endpoint response:

```python
{
  "records": [...],
  "document_validity": {
    "is_valid": bool,         # True if in whitelist
    "detected_type": str,     # "loa", "cc", "pcc", "financial closure", or whatever was detected
    "confidence": str,        # "high", "medium", or "low"
    "message": str | None     # Optional custom message (falls back to default)
  }
}
```

### Backend Implementation Approach

You have two options:

**Option 1: Add to extraction prompt** (Recommended)
Ask Gemini to classify the document type alongside field extraction:
```python
prompt += """
Additionally, classify this document type. Return one of:
- "letter of award (loa)"
- "completion certificate (cc)"  
- "provisional completion certificate (pcc)"
- "financial closure"
- "other"

Include this in your JSON response as: "document_type": "<classification>"
"""
```

Then in `extract_file_records()`, check the returned `document_type` and build the `document_validity` object.

**Option 2: Separate classification pass**
Run a quick classification prompt before the full extraction if you want to abort even earlier.

## 📋 Current Behavior Summary

### When `is_valid: false`:
1. ✅ Extraction completes (LLM must run to detect type)
2. ✅ Progress bar shows "✓ Extraction complete"
3. ✅ Results panel remains **hidden**
4. ✅ Amber warning banner appears with detected type
5. ✅ User can:
   - Upload different file (clears everything, opens file picker)
   - Force extract anyway (dismisses banner, shows hidden results)

### When `is_valid: true, confidence: low`:
1. ✅ Blue info banner shows
2. ✅ Results render normally
3. ✅ User can review but is warned to verify accuracy

### When `is_valid: true, confidence: high/medium`:
1. ✅ No banner
2. ✅ Results render normally

## 🎨 UI Match to Requirements

✅ Cream background `#FFFDF5`
✅ Amber border `#F59E0B` (4px left accent)
✅ Warning icon ⚠️
✅ Detected type shown in title
✅ Primary button (amber `#F59E0B`, white text)
✅ Secondary button (white bg, slate text, gray border)
✅ Proper spacing and hover states
✅ Matches existing design system

---

**Remove the mock code block before deploying to production!**

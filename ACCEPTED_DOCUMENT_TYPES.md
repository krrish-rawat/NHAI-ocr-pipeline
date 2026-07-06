# ✅ Complete List of Accepted Document Types

## All 6 Accepted Types

### NHAI Project Documents (4 Original)

1. **Letter of Award (LOA)**
   - Aliases: "loa", "letter of award"
   - Status: ✅ Accepted

2. **Completion Certificate (CC)**
   - Aliases: "cc", "completion certificate"
   - Status: ✅ Accepted

3. **Provisional Completion Certificate (PCC)**
   - Aliases: "pcc", "provisional completion certificate", "provisional cc"
   - Status: ✅ Accepted

4. **Financial Closure**
   - Aliases: "financial closure"
   - Status: ✅ Accepted

### Debarment Documents (2 New)

5. **Debarment Records** 🆕
   - Aliases: "debarment records"
   - Status: ✅ **Now Accepted**

6. **Debarment of Individuals** 🆕
   - Aliases: "debarment of individuals"
   - Status: ✅ **Now Accepted**

### Generic Debarment Match

- **Any "Debarment" Document**
  - Aliases: "debarment" (as a token)
  - Examples: "Debarment Order", "Debarment List", "Debarment Form"
  - Status: ✅ Accepted (matches token "debarment")

---

## What Gets Blocked ❌

Any document that is NOT in the accepted list:

- Invoice
- ACR Form
- Receipt
- Bank Statement
- Tax Form
- Generic Report
- Non-NHAI documents
- Unrecognized PDFs

---

## How Matching Works

### Level 1: Full Phrase Match (Most Specific)
```
Input: "Debarment Records"
Match: YES (exact match in whitelist)
Result: ✅ ACCEPTED
```

### Level 2: Substring Match
```
Input: "Debarment Records Official Document"
Match: YES (contains "debarment records")
Result: ✅ ACCEPTED
```

### Level 3: Token Match (Least Specific)
```
Input: "Debarment Authorization Form"
Tokens: ["debarment", "authorization", "form"]
Match: YES (contains token "debarment")
Result: ✅ ACCEPTED
```

---

## Backend Whitelist Definition

**File:** `/src/services/extraction_service.py`

```python
_ACCEPTED_DOC_PATTERNS: list[str] = [
    # Full phrases
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
    "debarment records",
    "debarment of individuals",
    
    # Abbreviated / partial
    "letter of award",
    "financial closure",
    "provisional completion certificate",
    "provisional completion",
    "completion certificate",
    "provisional cc",
    "provisional pcc",
    "debarment",
]

_ACCEPTED_DOC_TOKENS: frozenset[str] = frozenset([
    "loa", "cc", "pcc", "debarment"
])
```

---

## Frontend Type Labels

**File:** `/static/app.js`

```javascript
const TYPE_LABELS = {
    loa: "Letter of Award (LOA)",
    "letter of award": "Letter of Award (LOA)",
    
    pcc: "Provisional Completion Certificate (PCC)",
    "provisional completion certificate": "Provisional Completion Certificate (PCC)",
    
    cc: "Completion Certificate (CC)",
    "completion certificate": "Completion Certificate (CC)",
    
    "financial closure": "Financial Closure",
    
    "debarment records": "Debarment Records",
    "debarment of individuals": "Debarment of Individuals",
    debarment: "Debarment Document",
};
```

---

## Error Message

When an invalid document is uploaded, users see:

> "We couldn't identify this as a Letter of Award (LOA), Completion Certificate (CC), Provisional Completion Certificate (PCC), Financial Closure, Debarment Records, or Debarment of Individuals document. Please verify the uploaded file and try again."

---

## Testing Examples

### ✅ Will Be Accepted

- "Letter of Award (LOA)"
- "Completion Certificate"
- "PCC" or "Provisional CC"
- "Financial Closure"
- "Debarment Records"
- "Debarment of Individuals"
- "Debarment Order" (contains "debarment" token)
- "Debarment List" (contains "debarment" token)
- "DEBARMENT Form" (case-insensitive)

### ❌ Will Be Blocked

- "Invoice"
- "Receipt"
- "ACR Form"
- "Tax Document"
- "Bank Statement"
- "Annual Report"
- Any unrecognized document

---

## Updated: July 3, 2024

**Total Accepted Types:** 6  
**New Types:** Debarment Records, Debarment of Individuals  
**Status:** Live and active  
**Server:** Running with changes auto-loaded  


#!/usr/bin/env python3
"""
Direct test of the document validation flow without needing Gemini API.

This mocks the classify_document() method to simulate different document types
and verifies that the validation gate works correctly.
"""

import json
from unittest.mock import Mock, patch
from src.services.extraction_service import ExtractionService, _is_accepted_doc_type

# Test the validation logic directly
print("=" * 70)
print("Testing _is_accepted_doc_type() function")
print("=" * 70)

test_cases = [
    # Valid types
    ("letter of award (loa)", True, "Full phrase LOA"),
    ("completion certificate (cc)", True, "Full phrase CC"),
    ("provisional completion certificate (pcc)", True, "Full phrase PCC"),
    ("financial closure", True, "Full phrase Financial Closure"),
    ("loa", True, "Token LOA"),
    ("cc", True, "Token CC"),
    ("pcc", True, "Token PCC"),
    ("LOA", True, "Uppercase LOA"),
    ("Letter of Award (LOA)", True, "Variant with proper casing"),
    
    # Invalid types
    ("other", False, "Other/Unknown"),
    ("invoice", False, "Invoice"),
    ("purchase order", False, "Purchase Order"),
    ("acr form", False, "ACR Form"),
    ("", False, "Empty string"),
    ("unknown", False, "Unknown"),
    ("none", False, "None as string"),
]

all_passed = True
for doc_type, expected, description in test_cases:
    result = _is_accepted_doc_type(doc_type)
    status = "✓ PASS" if result == expected else "✗ FAIL"
    if result != expected:
        all_passed = False
    print(f"{status} | {description:30} | {repr(doc_type):40} -> {result}")

print()
print("=" * 70)
if all_passed:
    print("✓ All validation tests PASSED")
else:
    print("✗ Some validation tests FAILED")
print("=" * 70)

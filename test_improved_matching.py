#!/usr/bin/env python3
"""Test improved validation matching logic"""

ACCEPTED_TYPES = [
    "letter of award (loa)",
    "completion certificate (cc)",
    "provisional completion certificate (pcc)",
    "financial closure",
]

test_cases = [
    ("Letter of Award (LOA)", True),
    ("LOA", True),
    ("loa", True),
    ("Completion Certificate", True),
    ("CC", True),
    ("cc", True),
    ("Provisional CC", True),
    ("Provisional Completion Certificate", True),
    ("PCC", True),
    ("pcc", True),
    ("PCC Document", True),
    ("Financial Closure", True),
    ("financial closure", True),
    ("Invoice", False),
    ("Other", False),
    ("Purchase Order", False),
    ("Debarment Order", False),
]

print("=" * 70)
print("IMPROVED VALIDATION MATCHING TEST")
print("=" * 70)

for test_type, expected in test_cases:
    doc_type_normalized = test_type.lower().strip()
    
    # Improved validation logic matching the backend
    is_valid = (
        doc_type_normalized in ACCEPTED_TYPES or  # Exact match with full phrase
        any(accepted in doc_type_normalized for accepted in ACCEPTED_TYPES) or  # Substring
        doc_type_normalized in ["loa", "cc", "pcc"] or  # Pure abbreviations
        "letter of award" in doc_type_normalized or
        "completion certificate" in doc_type_normalized or
        "provisional" in doc_type_normalized and ("cc" in doc_type_normalized or "completion" in doc_type_normalized or "pcc" in doc_type_normalized) or
        "financial closure" in doc_type_normalized
    )
    
    matches_expected = is_valid == expected
    status_symbol = "✓" if is_valid else "✗"
    match_symbol = "✓" if matches_expected else "❌ WRONG"
    
    print(f"{status_symbol} {match_symbol:10} | Expected: {str(expected):5} | Got: {str(is_valid):5} | '{test_type}'")

print("=" * 70)

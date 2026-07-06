#!/usr/bin/env python3
"""Test final _is_accepted_doc_type helper function"""

_ACCEPTED_DOC_PATTERNS = [
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

_ACCEPTED_DOC_TOKENS = frozenset(["loa", "cc", "pcc"])

def _is_accepted_doc_type(raw_type):
    if not raw_type:
        return False
    normalized = raw_type.lower().strip()
    if any(pattern in normalized for pattern in _ACCEPTED_DOC_PATTERNS):
        return True
    tokens = set(normalized.split())
    if tokens & _ACCEPTED_DOC_TOKENS:
        return True
    return False

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
    ("other", False),
]

print("=" * 70)
print("FINAL VALIDATION TEST (_is_accepted_doc_type)")
print("=" * 70)

all_pass = True
for test_type, expected in test_cases:
    result = _is_accepted_doc_type(test_type)
    matches = result == expected
    status_symbol = "✓" if result else "✗"
    match_symbol = "✓ PASS" if matches else "❌ FAIL"
    
    if not matches:
        all_pass = False
    
    print(f"{status_symbol} {match_symbol:10} | Expected: {str(expected):5} | Got: {str(result):5} | '{test_type}'")

print("=" * 70)
if all_pass:
    print("✅ ALL TESTS PASSED")
else:
    print("❌ SOME TESTS FAILED")
print("=" * 70)

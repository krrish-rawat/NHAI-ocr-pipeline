"""Integration tests: end-to-end extraction against real Mistral API calls.

These tests use the anonymized fixture PDFs in tests/fixtures/ (synthetic
content only — no real PII) and exercise the FULL pipeline (OCR → classify →
extract) through build_pipeline(settings), which makes live Mistral API calls.

Requires MISTRAL_API_KEY to be set in the environment / .env file. If the key
is absent, these tests are skipped rather than failed, since they depend on
external network access and a paid API.
"""
import os
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.services.pipeline import build_pipeline
from src.services.settings import AppSettings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# AppSettings reads MISTRAL_API_KEY via pydantic-settings' own .env loader,
# but the skip condition below runs before any AppSettings is instantiated,
# so we explicitly load .env here to check for the key's presence.
load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.getenv("MISTRAL_API_KEY"),
    reason="MISTRAL_API_KEY not set — skipping live integration tests",
)


@pytest.fixture(scope="module")
def pipeline():
    settings = AppSettings()
    return build_pipeline(settings)


@pytest.fixture(autouse=True)
def _throttle_between_tests():
    """Space out live API calls to avoid tripping Mistral's free-tier rate limit.

    Each test issues 3+ Mistral calls (OCR + classify + N field extractions).
    A delay between tests keeps us under the free-tier requests-per-minute cap.
    """
    yield
    time.sleep(20)


# Task 20.2 — test_loa_extraction_known_values
def test_loa_extraction_known_values(pipeline):
    """Upload the LOA fixture and confirm known field values are extracted.

    The LOA fixture contains "M/s Fictional Construction Pvt Ltd" as the
    contractor name and "15.03.2024" as the agreement date, both embedded in
    prose sentences (no adjacent label) — validates verbatim grounding works
    on a real (if synthetic) tabular/prose-mixed document.
    """
    pdf_path = str(FIXTURES_DIR / "loa_sample.pdf")
    response = pipeline.run(
        pdf_path,
        "loa_sample.pdf",
        ["Contractor Name", "Agreement Date"],
        force_extract=False,
    )

    assert response.doc_type == "letter of award (loa)"
    record = response.records[0]
    assert record.status == "success"

    contractor = record.fields["Contractor Name"].value
    agreement_date = record.fields["Agreement Date"].value

    assert contractor != "Null", "Expected contractor name to be extracted from LOA"
    assert "Fictional Construction" in contractor
    assert agreement_date != "Null", "Expected agreement date to be extracted from LOA"
    assert "15.03.2024" in agreement_date


# Task 20.3 — test_financial_closure_prose_values
def test_financial_closure_prose_values(pipeline):
    """Upload the financial closure fixture and confirm prose-embedded values
    are extracted without requiring an adjacent explicit label.

    This is the direct regression test for the R4 semantic-grounding fix:
    the fixture states "The total project cost stands at Rs. 500.00 Crore,
    of which the lender contribution amounts to Rs. 350.00 Crore" with NO
    adjacent "Total Project Cost:" or "Lender Contribution:" label — the
    extractor must identify each value semantically from sentence context,
    and must NOT confuse the two similar Crore amounts in the same sentence.
    """
    pdf_path = str(FIXTURES_DIR / "financial_closure_sample.pdf")
    response = pipeline.run(
        pdf_path,
        "financial_closure_sample.pdf",
        ["Total Project Cost", "Lender Contribution"],
        force_extract=False,
    )

    assert response.doc_type == "financial closure"
    record = response.records[0]
    assert record.status == "success"

    project_cost = record.fields["Total Project Cost"].value
    lender_contribution = record.fields["Lender Contribution"].value

    assert project_cost != "Null", (
        "Semantic grounding should extract 'Rs. 500.00 Crore' from prose "
        "even without an adjacent 'Total Project Cost:' label"
    )
    assert "500" in project_cost
    assert lender_contribution != "Null"
    assert "350" in lender_contribution
    # Critically: the two similar amounts in the same sentence must not be swapped
    assert "500" not in lender_contribution
    assert "350" not in project_cost


# Task 20.4 — test_debarment_extraction
def test_debarment_extraction(pipeline):
    """Upload the debarment fixture and confirm name and PAN are found.

    This fixture is tabular (label: value pairs), which is the original
    success case the grounding rules were built around — confirms the
    semantic-grounding rewrite did not regress the tabular path.
    """
    pdf_path = str(FIXTURES_DIR / "debarment_sample.pdf")
    response = pipeline.run(
        pdf_path,
        "debarment_sample.pdf",
        ["Name", "PAN"],
        force_extract=False,
    )

    assert response.doc_type == "debarment records"
    record = response.records[0]
    assert record.status == "success"

    name = record.fields["Name"].value
    pan = record.fields["PAN"].value

    assert name != "Null"
    assert "Test Fictitious Kumar" in name
    assert pan != "Null"
    assert "ABCDE1234F" in pan


# Task 20.5 — test_other_document_rejected
def test_other_document_rejected(pipeline):
    """Upload a non-NHAI invoice without force_extract and confirm rejection.

    Validates the Phase 1 classification gate: an invoice must be classified
    as "other" and extraction must be blocked (status="rejected") with a
    non-empty failure_reason.
    """
    pdf_path = str(FIXTURES_DIR / "non_nhai_invoice_sample.pdf")
    response = pipeline.run(
        pdf_path,
        "non_nhai_invoice_sample.pdf",
        ["Name"],
        force_extract=False,
    )

    assert response.doc_type not in (
        "letter of award (loa)",
        "completion certificate (cc)",
        "provisional completion certificate (pcc)",
        "financial closure",
        "debarment records",
    )
    record = response.records[0]
    assert record.status == "rejected"
    assert record.failure_reason != ""
    # All fields must remain Null since extraction was blocked
    assert record.fields["Name"].value == "Null"


def test_other_document_force_extract_bypasses_gate(pipeline):
    """Sanity check for the Force Extract override: the same invoice with
    force_extract=True must proceed past the classification gate."""
    pdf_path = str(FIXTURES_DIR / "non_nhai_invoice_sample.pdf")
    response = pipeline.run(
        pdf_path,
        "non_nhai_invoice_sample.pdf",
        ["Item"],
        force_extract=True,
    )

    record = response.records[0]
    assert record.status != "rejected"

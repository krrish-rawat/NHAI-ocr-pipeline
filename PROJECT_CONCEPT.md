# NHAI PDF Data Extraction — Project Concept

> A distilled concept summary of the existing prototype, intended as the
> starting point for a fresh, requirements-driven, production-grade rebuild.

---

## 1. The Problem

The National Highways Authority of India (NHAI) publishes large volumes of
official PDF documents — debarment/blacklisting orders, Letters of Award (LOA),
completion certificates (CC/PCC), financial closure records, and similar.

These documents are:
- **Mostly scanned images** (photographed paper), so they have no selectable
  text layer.
- **Bilingual** (English + Hindi).
- **Semi-structured** — key facts live in tables and labeled clauses
  (Name, Date of Birth, PAN, Infracon ID, Mobile, dates, project references).

Manually reading each PDF and copying fields into a spreadsheet is slow,
error-prone, and does not scale across thousands of documents.

## 2. The Idea

A web tool where an operator:
1. Uploads one (or more) NHAI PDF(s).
2. Specifies which fields to extract (e.g. "Name", "Date of Birth", "PAN").
3. Receives clean structured output (JSON / CSV / Excel) with each field's
   value — and ideally a citation showing where in the document it was found.

The system should reject documents that are not recognized NHAI document types
(cheap pre-check) before spending effort on full extraction.

## 3. Core Concept & Pipeline

The winning insight from the prototype: **convert the PDF to structured text
once, then let an LLM reason over the text** — instead of repeatedly sending
heavy page images to a vision model.

```
PDF upload
   │
   ▼
[OCR]  Convert PDF → structured markdown text  (handles scanned + native PDFs)
   │
   ▼
[Phase 1 — Classify]  Is this a valid NHAI document type?  → reject early if not
   │  (valid)
   ▼
[Phase 2 — Extract]   Pull the requested fields from the text, grounded in
                       verbatim source phrases (no hallucinated values)
   │
   ▼
Structured response (JSON / CSV / Excel), optionally with source citations
```

### Design principles proven out in the prototype
- **Text-first, not image-first** — cuts latency dramatically (~24s → ~4-7s).
- **Two-phase gate** — classify cheaply before extracting, to reject invalid
  docs and save cost.
- **Strict grounding** — every extracted value must map to a verbatim phrase in
  the source text; return "Null" rather than guess. Reduces hallucination.
- **Graceful fallback** — if the fast OCR path fails, fall back to an
  image-based path rather than failing the request.
- **Provider-swappable LLM** — the extraction "brain" should be behind an
  interface so the model/provider can be changed without touching orchestration.

## 4. Key Domain Rules

- **Accepted document types**: Letter of Award (LOA), Completion Certificate
  (CC), Provisional Completion Certificate (PCC), Financial Closure, Debarment /
  Blacklisting / Restriction-from-participation records. Everything else → "other"
  and is blocked (with an operator override option).
- **Field ambiguity**: documents often contain many similar values (7+ dates,
  multiple names). Extraction must match each field to the clause that
  explicitly labels it — never borrow a plausible-looking value from elsewhere.
- **Output shape stability**: downstream consumers depend on a stable JSON/CSV
  schema (`source_file`, one column per attribute, `status`, `failure_reason`).
- **Bounding-box citations** (optional/nice-to-have): highlight where a value
  was found in the original PDF for verification.

## 5. Non-Functional Expectations

| Concern | Target |
|---------|--------|
| Latency | ≤ 10s per single-document extraction of 5-7 fields |
| Accuracy | High grounding fidelity; prefer "Null" over a wrong value |
| File limits | Enforced max upload size (was 25 MB) |
| Languages | English + Hindi document content |
| Privacy | Documents contain real PII — must be handled/retained responsibly |

## 6. What the Prototype Got Right (keep these)
- Text-first OCR → LLM pipeline concept.
- Two-phase classify-then-extract flow.
- Strict grounding prompt discipline.
- Fallback path for resilience.
- Clean, single-column government-styled UI with bilingual (EN/HI) toggle.
- Provider abstraction for the LLM client.

## 7. What to Fix in the Rebuild (do these properly from the start)
- **Requirements-first**: define scope, accepted doc types, field catalog, and
  output contract before coding.
- **Single, clean provider strategy** (don't leave dead Gemini + Mistral paths).
- **Automated tests** — unit + property-based tests for extraction correctness,
  schema stability, and the classify gate.
- **Security** — authentication, rate limiting, remove debug endpoints from prod.
- **PII handling** — explicit retention/deletion policy; never commit sample
  PDFs to source control; scrub temp files reliably.
- **Observability** — health checks, structured logging, basic metrics.
- **Config & secrets** — proper secret management, not `.env` committed near code.
- **Persistence/queue** (if scaling) — move beyond single-process in-memory state.
- **Documentation** — README, API contract, deployment guide.

## 8. Current Prototype Production Rating

**4 / 10** — a functional, reasonably fast MVP that demos well, but lacks
tests, auth, observability, and carries dead code from organic evolution.
Suitable as a proof-of-concept and reference, not as a deployable government
service.

---

*This document captures the concept only. The rebuild will start fresh with a
proper Requirements → Design → Tasks spec workflow.*

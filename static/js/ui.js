// Main UI controller: wires the DOM to api.js, validation.js, progress.js, lang.js.
// This is the entry point loaded last; it drives the whole page.

import { postExtract } from "./api.js";
import { validateFile, validateFields, splitFields } from "./validation.js";
import { showProgress, updateProgress, hideProgress } from "./progress.js";
import { applyLanguage, initLangToggle, getCurrentLang } from "./lang.js";

// ── DOM references ───────────────────────────────────────────────────────────
const pdfInput = document.getElementById("pdf-input");
const fieldsInput = document.getElementById("fields-input");
const extractBtn = document.getElementById("extract-btn");

const rejectionBanner = document.getElementById("rejection-banner");
const rejectionDocType = document.getElementById("rejection-doc-type");
const forceExtractBtn = document.getElementById("force-extract-btn");

const resultsCard = document.getElementById("results-card");
const docTypeLabel = document.getElementById("doc-type-label");
const resultsTable = document.getElementById("results-table");
const resultsTbody = resultsTable ? resultsTable.querySelector("tbody") : null;

const downloadJsonBtn = document.getElementById("download-json-btn");
const downloadCsvBtn = document.getElementById("download-csv-btn");

// ── State ─────────────────────────────────────────────────────────────────────
let _lastJsonResponse = null; // cached last successful extraction result

// ── Error display ────────────────────────────────────────────────────────────
function showErrorMessage(msg) {
  // Reuse the rejection banner styling for generic errors since there's no
  // separate error element in the markup.
  hideResultsCard();
  if (rejectionDocType) rejectionDocType.textContent = msg;
  if (forceExtractBtn) forceExtractBtn.style.display = "none";
  if (rejectionBanner) rejectionBanner.style.display = "flex";
}

function clearRejectionBanner() {
  if (rejectionBanner) rejectionBanner.style.display = "none";
  if (forceExtractBtn) forceExtractBtn.style.display = "";
}

// ── Results rendering ─────────────────────────────────────────────────────────
function hideResultsCard() {
  if (resultsCard) resultsCard.style.display = "none";
}

function confidenceBadge(confidence) {
  const cls = `conf-${confidence || "unknown"}`;
  return `<span class="conf-badge ${cls}">${confidence || "unknown"}</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderFieldTable(fieldNames, records) {
  if (!resultsTbody) return;
  resultsTbody.innerHTML = "";

  // Single-document flow: use the first record (multi-file not exposed in this UI)
  const record = records && records.length ? records[0] : null;
  if (!record) return;

  fieldNames.forEach((fn) => {
    const fieldData = record.fields ? record.fields[fn] : null;
    const value = fieldData ? fieldData.value : "Null";
    const confidence = fieldData && fieldData.source_meta ? fieldData.source_meta.confidence : "unknown";

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(fn)}</td>
      <td>${escapeHtml(value)}</td>
      <td>${confidenceBadge(confidence)}</td>
    `;
    resultsTbody.appendChild(tr);
  });
}

function showResultsCard(response) {
  if (!resultsCard) return;
  clearRejectionBanner();

  if (docTypeLabel) docTypeLabel.textContent = response.doc_type || "";
  renderFieldTable(response.field_names || [], response.records || []);

  resultsCard.style.display = "block";
  _lastJsonResponse = response;
}

function showRejectionBanner(docType, onForceExtract) {
  hideResultsCard();
  if (rejectionDocType) {
    rejectionDocType.textContent = docType ? `Detected type: "${docType}"` : "";
  }
  if (forceExtractBtn) {
    forceExtractBtn.style.display = "";
    // Remove any previous handler before attaching a new one
    forceExtractBtn.onclick = onForceExtract;
  }
  if (rejectionBanner) rejectionBanner.style.display = "flex";
}

// ── Form submission ───────────────────────────────────────────────────────────
async function runExtraction(forceExtract = false) {
  const file = pdfInput && pdfInput.files ? pdfInput.files[0] : null;
  const fieldsText = fieldsInput ? fieldsInput.value : "";

  const fileError = validateFile(file);
  if (fileError) {
    showErrorMessage(fileError);
    return;
  }

  const fieldsError = validateFields(fieldsText);
  if (fieldsError) {
    showErrorMessage(fieldsError);
    return;
  }

  clearRejectionBanner();
  hideResultsCard();

  const formData = new FormData();
  formData.append("file", file);
  formData.append("fields", fieldsText);
  formData.append("output_format", "json");
  formData.append("force_extract", forceExtract ? "true" : "false");

  if (extractBtn) extractBtn.disabled = true;
  showProgress("Uploading and processing document…");

  try {
    const result = await postExtract(formData);

    if (result.type === "json") {
      const response = result.data;
      const record = response.records && response.records[0];

      if (record && record.status === "rejected") {
        showRejectionBanner(response.doc_type, () => runExtraction(true));
      } else {
        showResultsCard(response);
      }
    }
  } catch (err) {
    showErrorMessage(err.message || "Extraction failed. Please try again.");
  } finally {
    hideProgress();
    if (extractBtn) extractBtn.disabled = false;
  }
}

// ── Download handlers ─────────────────────────────────────────────────────────
function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadJson() {
  if (!_lastJsonResponse) return;
  const blob = new Blob([JSON.stringify(_lastJsonResponse, null, 2)], {
    type: "application/json",
  });
  triggerBlobDownload(blob, "extracted.json");
}

async function downloadCsv() {
  const file = pdfInput && pdfInput.files ? pdfInput.files[0] : null;
  const fieldsText = fieldsInput ? fieldsInput.value : "";
  if (!file || !fieldsText) return;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("fields", fieldsText);
  formData.append("output_format", "csv");
  formData.append("force_extract", "true"); // already passed validation once

  try {
    const result = await postExtract(formData);
    if (result.type === "csv") {
      triggerBlobDownload(result.blob, "extracted.csv");
    }
  } catch (err) {
    showErrorMessage(err.message || "CSV download failed.");
  }
}

// ── Event wiring ──────────────────────────────────────────────────────────────
if (extractBtn) {
  extractBtn.addEventListener("click", () => runExtraction(false));
}
if (downloadJsonBtn) {
  downloadJsonBtn.addEventListener("click", downloadJson);
}
if (downloadCsvBtn) {
  downloadCsvBtn.addEventListener("click", downloadCsv);
}

// ── Init ──────────────────────────────────────────────────────────────────────
initLangToggle();
applyLanguage(getCurrentLang());

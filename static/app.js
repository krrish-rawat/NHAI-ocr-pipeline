// ─── DOM references ──────────────────────────────────────────────────────────
const extractForm        = document.querySelector("#extractForm");
const submitButton       = document.querySelector("#submitButton");
const btnLabel           = document.querySelector("#btnLabel");
const btnSpinner         = document.querySelector("#btnSpinner");
const message            = document.querySelector("#message");
const statusPill         = document.querySelector("#statusPill");
const statusText         = statusPill.querySelector(".status-text");
const resultForm         = document.querySelector("#resultForm");
const summaryPlaceholder = document.querySelector("#summaryPlaceholder");
const summaryPanel       = document.querySelector("#summaryPanel");
const dropzone           = document.querySelector("#dropzone");
const fileInput          = document.querySelector("#files");
const fileList           = document.querySelector("#fileList");
const fileSuccessPanel   = document.querySelector("#fileSuccessPanel");
const fileSuccessLabel   = document.querySelector("#fileSuccessLabel");
const clearFilesBtn      = document.querySelector("#clearFilesBtn");

// Progress bar elements
const progressContainer = document.querySelector("#progressContainer");
const progressFill      = document.querySelector("#progressFill");
const progressPct       = document.querySelector("#progressPct");
const progressStatus    = document.querySelector("#progressStatus");
const progressTimer     = document.querySelector("#progressTimer");
const progressBarTrack  = document.querySelector("#progressBarTrack");

// PDF modal elements
const pdfModal       = document.querySelector("#pdfModal");
const pdfModalClose  = document.querySelector("#pdfModalClose");
const pdfModalTitle  = document.querySelector("#pdfModalTitle");
const pdfPageInfo    = document.querySelector("#pdfPageInfo");
const pdfCanvas      = document.querySelector("#pdfCanvas");
const pdfViewerWrap  = document.querySelector("#pdfViewerWrap");
const pdfHighlight   = document.querySelector("#pdfHighlight");
const pdfTooltip     = document.querySelector("#pdfTooltip");
const pdfErrorMsg    = document.querySelector("#pdfErrorMsg");

// ─── State ───────────────────────────────────────────────────────────────────
let allRecords   = [];
let currentIndex = 0;
let summaryRequestId = 0;

// Tracks the current FileList-compatible array for submission
let selectedFiles = [];

// ─── Progress bar controller ─────────────────────────────────────────────────
const PROGRESS_MESSAGES = [
  "Reading PDF document...",
  "Analyzing text content...",
  "Structuring extracted data...",
];

const Progress = (() => {
  let _pct         = 0;
  let _target      = 0;
  let _animFrame   = null;
  let _msgInterval = null;
  let _timerInterval = null;
  let _msgIndex    = 0;
  let _startTime   = 0;
  let _estimatedMs = 20000; // initial estimate: 20 s

  function _setFill(pct) {
    _pct = pct;
    progressFill.style.width   = `${pct}%`;
    progressPct.textContent    = `${Math.round(pct)}%`;
    progressBarTrack.setAttribute("aria-valuenow", Math.round(pct));
  }

  function _tick() {
    if (_pct < _target) {
      _setFill(Math.min(_pct + 0.4, _target));
      _animFrame = requestAnimationFrame(_tick);
    }
  }

  function _updateTimer() {
    const elapsed  = Date.now() - _startTime;
    const fraction = Math.max(_pct / 100, 0.01);
    const totalEst = elapsed / fraction;
    const remaining = Math.max(Math.round((totalEst - elapsed) / 1000), 1);
    progressTimer.textContent = `Estimated time: ${remaining} second${remaining !== 1 ? "s" : ""} remaining`;
  }

  return {
    start(estimatedMs = 20000) {
      _estimatedMs = estimatedMs;
      _startTime   = Date.now();
      _pct = 0; _target = 0; _msgIndex = 0;
      progressFill.classList.remove("is-error");
      progressPct.classList.remove("is-error");
      _setFill(0);
      progressContainer.hidden = false;

      // Rotate status messages
      progressStatus.textContent = PROGRESS_MESSAGES[0];
      _msgInterval = setInterval(() => {
        _msgIndex = (_msgIndex + 1) % PROGRESS_MESSAGES.length;
        progressStatus.textContent = PROGRESS_MESSAGES[_msgIndex];
      }, 1500);

      // Timer countdown
      _updateTimer();
      _timerInterval = setInterval(_updateTimer, 1000);

      // Simulate smooth progress up to 90% over estimatedMs
      const step = () => {
        const elapsed = Date.now() - _startTime;
        const natural = Math.min((elapsed / _estimatedMs) * 90, 90);
        if (natural > _target) {
          _target = natural;
          cancelAnimationFrame(_animFrame);
          _animFrame = requestAnimationFrame(_tick);
        }
        if (_pct < 90) setTimeout(step, 300);
      };
      setTimeout(step, 300);
    },

    advance(pct) {
      _target = Math.min(pct, 95); // never reach 100 until done() called
      cancelAnimationFrame(_animFrame);
      _animFrame = requestAnimationFrame(_tick);
    },

    done() {
      clearInterval(_msgInterval);
      clearInterval(_timerInterval);
      _target = 100;
      cancelAnimationFrame(_animFrame);
      _animFrame = requestAnimationFrame(_tick);
      progressStatus.textContent = "✓ Extraction complete";
      progressTimer.textContent  = "";
      setTimeout(() => {
        progressContainer.style.transition = "opacity 0.5s ease";
        progressContainer.style.opacity    = "0";
        setTimeout(() => {
          progressContainer.hidden          = true;
          progressContainer.style.opacity   = "";
          progressContainer.style.transition = "";
        }, 500);
      }, 1000);
    },

    error() {
      clearInterval(_msgInterval);
      clearInterval(_timerInterval);
      cancelAnimationFrame(_animFrame);
      progressFill.classList.add("is-error");
      progressPct.classList.add("is-error");
      progressStatus.textContent = "Processing failed";
      progressTimer.textContent  = "";
    },

    reset() {
      clearInterval(_msgInterval);
      clearInterval(_timerInterval);
      cancelAnimationFrame(_animFrame);
      progressContainer.hidden  = true;
      progressContainer.style.opacity    = "";
      progressContainer.style.transition = "";
      progressFill.classList.remove("is-error");
      progressPct.classList.remove("is-error");
      _setFill(0);
    },
  };
})();

// ─── PDF Citation Modal ──────────────────────────────────────────────────────
// Requires PDF.js loaded globally (pdfjsLib)
const PdfModal = (() => {
  let _pdfDoc      = null;
  let _fileUrl     = null;
  let _tooltipTimer = null;

  // Configure PDF.js worker (uses same CDN version)
  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  }

  function _show()  { pdfModal.hidden = false; document.body.style.overflow = "hidden"; }
  function _hide()  { pdfModal.hidden = true;  document.body.style.overflow = ""; _cleanup(); }

  function _cleanup() {
    clearTimeout(_tooltipTimer);
    pdfHighlight.hidden = true;
    pdfTooltip.hidden   = true;
    pdfErrorMsg.hidden  = true;
  }

  async function _renderPage(pageNum) {
    if (!_pdfDoc) return null;
    try {
      const page     = await _pdfDoc.getPage(pageNum);
      const scale    = Math.min(
        pdfViewerWrap.parentElement.clientWidth / page.getViewport({ scale: 1 }).width * 0.9,
        1.5
      );
      const viewport = page.getViewport({ scale });
      const ctx      = pdfCanvas.getContext("2d");
      pdfCanvas.width  = viewport.width;
      pdfCanvas.height = viewport.height;
      await page.render({ canvasContext: ctx, viewport }).promise;
      pdfPageInfo.textContent = `Page ${pageNum} of ${_pdfDoc.numPages}`;
      return viewport;   // caller uses this to place the highlight
    } catch {
      _showError("Unable to render this page.");
      return null;
    }
  }

  function _placeHighlight(bbox, renderedViewport) {
    if (!bbox || !renderedViewport) return;

    // renderedViewport is the viewport used when the canvas was rendered.
    // bbox coordinates are in PDF user-space (scale=1).
    // Convert using the rendered viewport's scale.
    const scale = renderedViewport.scale;
    const left  = bbox.x * scale;
    // PDF y=0 is bottom-left; canvas y=0 is top-left — flip the y axis.
    const top   = (renderedViewport.height / scale - bbox.y - bbox.height) * scale;
    const w     = bbox.width  * scale;
    const h     = bbox.height * scale;

    pdfHighlight.style.left   = `${left}px`;
    pdfHighlight.style.top    = `${top}px`;
    pdfHighlight.style.width  = `${w}px`;
    pdfHighlight.style.height = `${h}px`;
    pdfHighlight.hidden = false;

    // Tooltip centred above the highlight
    pdfTooltip.textContent     = "Source location";
    pdfTooltip.style.left      = `${left + w / 2}px`;
    pdfTooltip.style.top       = `${Math.max(top - 36, 4)}px`;
    pdfTooltip.style.transform = "translateX(-50%)";
    pdfTooltip.hidden = false;
    clearTimeout(_tooltipTimer);
    _tooltipTimer = setTimeout(() => { pdfTooltip.hidden = true; }, 4000);

    // Scroll into view after paint
    setTimeout(() => {
      pdfHighlight.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 150);
  }

  function _showError(msg) {
    pdfErrorMsg.textContent = msg;
    pdfErrorMsg.hidden = false;
    pdfCanvas.hidden   = true;
  }

  // Public: open modal for a given file blob URL + source metadata
  async function open(fileUrl, sourceData, fieldName) {
    _cleanup();
    pdfCanvas.hidden = false;
    pdfModalTitle.textContent = fieldName ? `Source — ${fieldName.replace(/_/g, " ")}` : "Source Document";
    pdfPageInfo.textContent   = "";
    _fileUrl = fileUrl;
    _show();

    if (typeof pdfjsLib === "undefined") {
      _showError("PDF viewer could not be loaded. Check your internet connection.");
      return;
    }

    try {
      _pdfDoc = await pdfjsLib.getDocument(fileUrl).promise;
      const pageNum = (sourceData?.pageNumber) || 1;
      const clampedPage = (pageNum >= 1 && pageNum <= _pdfDoc.numPages) ? pageNum : 1;

      if (clampedPage !== pageNum) {
        const renderedVp = await _renderPage(1);
        _showError(`Page ${pageNum} is out of range. Showing page 1.`);
        return;
      }

      const renderedVp = await _renderPage(clampedPage);

      if (sourceData?.boundingBox && renderedVp) {
        _placeHighlight(sourceData.boundingBox, renderedVp);
      } else {
        // No bounding box — show a generic tooltip so the user knows
        // the PDF opened but precise highlighting isn't available.
        pdfTooltip.textContent     = "Source location unavailable — showing full page";
        pdfTooltip.style.left      = "50%";
        pdfTooltip.style.top       = "8px";
        pdfTooltip.style.transform = "translateX(-50%)";
        pdfTooltip.hidden = false;
        clearTimeout(_tooltipTimer);
        _tooltipTimer = setTimeout(() => { pdfTooltip.hidden = true; }, 4000);
      }
    } catch (err) {
      _showError("Unable to load PDF. The file may have been cleared from memory.");
    }
  }

  // Close handlers
  pdfModalClose.addEventListener("click", _hide);
  pdfModal.addEventListener("click", (e) => { if (e.target === pdfModal) _hide(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !pdfModal.hidden) _hide(); });

  return { open };
})();

// ─── Status pill ─────────────────────────────────────────────────────────────
function setStatus(state, label) {
  statusPill.className   = `status-pill status-${state}`;
  statusText.textContent = label;
}

// ─── Message ─────────────────────────────────────────────────────────────────
function setMessage(text, type = "") {
  message.textContent = text;
  message.className   = `field-message ${type}`.trim();
}

// ─── Busy state ───────────────────────────────────────────────────────────────
function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  btnLabel.textContent  = isBusy ? "Processing…" : "Extract Data";
  btnSpinner.hidden     = !isBusy;
  if (isBusy) setStatus("running", "Processing");
}

// ─── File size formatting ─────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024)       return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── File upload state management ────────────────────────────────────────────
/**
 * Call this whenever the file selection changes (input change or drop).
 * Switches the UI between the idle dropzone and the success panel.
 */
function applyFileSelection(files) {
  selectedFiles = Array.from(files);

  if (!selectedFiles.length) {
    // Reset to idle dropzone
    dropzone.hidden         = false;
    fileSuccessPanel.hidden = true;
    fileList.innerHTML      = "";
    return;
  }

  // Show success panel, hide dropzone
  dropzone.hidden         = true;
  fileSuccessPanel.hidden = false;

  // Summary label
  const count = selectedFiles.length;
  fileSuccessLabel.textContent = count === 1
    ? `${count} file ready`
    : `${count} files ready`;

  // Render file rows
  fileList.innerHTML = "";
  selectedFiles.forEach((file) => {
    const li = document.createElement("li");
    li.className = "file-pill";

    // PDF icon
    li.innerHTML = `
      <svg class="file-pill-icon" width="16" height="16" viewBox="0 0 16 16"
           fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <rect x="2" y="1" width="9" height="13" rx="0"
              stroke="#003580" stroke-width="1.2" fill="#EEF3FF"/>
        <path d="M9 1v4h4" stroke="#003580" stroke-width="1.2" fill="none"/>
        <line x1="4" y1="7" x2="9" y2="7" stroke="#003580" stroke-width="0.8"/>
        <line x1="4" y1="9" x2="9" y2="9" stroke="#003580" stroke-width="0.8"/>
        <line x1="4" y1="11" x2="7" y2="11" stroke="#003580" stroke-width="0.8"/>
      </svg>
      <span class="file-pill-name" title="${file.name}">${file.name}</span>
      <span class="file-pill-size">${formatBytes(file.size)}</span>
    `;
    fileList.appendChild(li);
  });
}

// Input change (click-to-select)
fileInput.addEventListener("change", () => applyFileSelection(fileInput.files));

// Remove / clear button
clearFilesBtn.addEventListener("click", () => {
  fileInput.value = "";
  selectedFiles   = [];
  applyFileSelection([]);
  resetSummaryDashboard();
  Progress.reset();
  setMessage("");
});

// ─── Drag and drop ────────────────────────────────────────────────────────────
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  const dt = e.dataTransfer;
  if (dt && dt.files.length) {
    // Sync the real input where possible
    try { fileInput.files = dt.files; } catch { /* not supported in all browsers */ }
    applyFileSelection(dt.files);
  }
});

// ─── Inline field builder ────────────────────────────────────────────────────
/**
 * Creates an editable field row for one extracted value.
 * The field is pre-populated with the extracted suggestion and shows an
 * edit-confirmation warning when the value is changed.
 *
 * @param {string} name       – field name (used as input id/name)
 * @param {string} suggestion – extracted value from the PDF
 * @param {HTMLElement} group – parent .result-field-group for dirty-state class
 * @param {object|null} source – citation source metadata (may be null)
 * @returns {HTMLElement} .field-input-row
 */
function createAutocompleteField(name, suggestion, group, source) {
  const wrapper = document.createElement("div");
  wrapper.className = "autocomplete-wrapper";

  // Real input — pre-populated with the extracted value (no ghost needed)
  const input = document.createElement("input");
  input.type         = "text";
  input.name         = name;
  input.id           = `field-${name}`;
  input.className    = "autocomplete-input";
  input.value        = suggestion;   // show value directly, no ghost
  input.autocomplete = "off";
  input.spellcheck   = false;
  input.setAttribute("aria-label", name.replace(/_/g, " "));

  // Edit confirmation warning
  const warning = document.createElement("div");
  warning.className = "edit-warning";
  warning.setAttribute("role", "alert");
  warning.setAttribute("aria-live", "polite");

  const warningText = document.createElement("span");
  warningText.className   = "edit-warning-text";
  warningText.textContent = "⚠️ Updating records after extraction may affect reporting. Continue?";

  const warningActions = document.createElement("span");
  warningActions.className = "edit-warning-actions";

  const cancelBtn = document.createElement("button");
  cancelBtn.type        = "button";
  cancelBtn.className   = "edit-warning-btn edit-warning-btn--cancel";
  cancelBtn.textContent = "Cancel";

  const updateBtn = document.createElement("button");
  updateBtn.type        = "button";
  updateBtn.className   = "edit-warning-btn edit-warning-btn--update";
  updateBtn.textContent = "Update";

  warningActions.appendChild(cancelBtn);
  warningActions.appendChild(updateBtn);
  warning.appendChild(warningText);
  warning.appendChild(warningActions);

  function syncWarning() {
    const isDirty = input.value !== suggestion;
    warning.classList.toggle("visible", isDirty);
    if (group) group.classList.toggle("is-dirty", isDirty);
  }

  cancelBtn.addEventListener("click", () => {
    input.value = suggestion;
    warning.classList.remove("visible");
    if (group) group.classList.remove("is-dirty");
  });

  updateBtn.addEventListener("click", () => {
    warning.classList.remove("visible");
  });

  input.addEventListener("input", syncWarning);

  wrapper.appendChild(input);
  wrapper.appendChild(warning);

  // Row: input wrapper + citation button
  const row = document.createElement("div");
  row.className = "field-input-row";
  row.appendChild(wrapper);

  // Citation button — always rendered; enabled if a PDF URL is available
  const citBtn = document.createElement("button");
  citBtn.type        = "button";
  citBtn.className   = "citation-link";
  citBtn.textContent = "🔗";
  citBtn.title       = source ? "View source in PDF" : "Open PDF";
  citBtn.setAttribute("aria-label",
    source
      ? `View source for ${name.replace(/_/g, " ")} in PDF`
      : `Open PDF for ${name.replace(/_/g, " ")}`
  );

  citBtn.addEventListener("click", () => {
    const fileUrl = resultForm.dataset.pdfUrl;
    if (!fileUrl) {
      alert("PDF is no longer available in memory. Please re-upload.");
      return;
    }
    // Pass source metadata if available; PdfModal handles null gracefully
    PdfModal.open(fileUrl, source ?? null, name);
  });

  row.appendChild(citBtn);
  return row;
}

// ─── Result form renderer ─────────────────────────────────────────────────────
function renderRecord(record, pdfUrl) {
  resultForm.innerHTML = "";
  // Store the object-URL so citation buttons can find it
  if (pdfUrl) resultForm.dataset.pdfUrl = pdfUrl;

  Object.entries(record).forEach(([key, value]) => {
    if (key === "source_file") return;
    if (key === "status" || key === "failure_reason") return;
    if (key === "source_meta") return;
    if (key === "_pdfUrl") return;  // internal blob URL, never shown

    const group = document.createElement("div");
    group.className = "result-field-group";

    const label = document.createElement("label");
    label.htmlFor     = `field-${key}`;
    label.textContent = key.replace(/_/g, " ");

    // Unsaved-change indicator dot
    const dot = document.createElement("span");
    dot.className = "unsaved-dot";
    dot.setAttribute("aria-hidden", "true");
    label.appendChild(dot);

    group.appendChild(label);

    // Pull per-field citation source if API returned source_meta
    const source = record.source_meta?.[key] ?? null;
    group.appendChild(createAutocompleteField(key, String(value ?? ""), group, source));
    resultForm.appendChild(group);
  });
}

function showRecord(index) {
  if (!allRecords.length) return;
  currentIndex = index;
  renderRecord(allRecords[index], resultForm.dataset.pdfUrl);
}

function showResultPanel(records, pdfUrl) {
  allRecords   = records;
  currentIndex = 0;

  resultForm.hidden = false;
  if (pdfUrl) resultForm.dataset.pdfUrl = pdfUrl;

  showRecord(0);
  setStatus("ready", "System Operational");
}

function resetSummaryDashboard() {
  summaryPanel.hidden = true;
  summaryPanel.innerHTML = "";
  summaryPlaceholder.hidden = false;
  summaryPlaceholder.querySelector(".summary-empty-title").textContent = "No document summary yet";
  summaryPlaceholder.querySelector(".summary-empty-sub").textContent = "A high-level PDF overview will appear after upload.";
}

function setSummaryLoading() {
  summaryPanel.hidden = true;
  summaryPanel.innerHTML = "";
  summaryPlaceholder.hidden = false;
  summaryPlaceholder.querySelector(".summary-empty-title").textContent = "Generating summary";
  summaryPlaceholder.querySelector(".summary-empty-sub").textContent = "Preparing a concise document overview.";
}

function renderSummaryDashboard(summaries) {
  summaryPanel.innerHTML = "";

  summaries.forEach((summary) => {
    const section = document.createElement("section");
    section.className = "summary-document";

    const title = document.createElement("h3");
    title.className = "summary-document-title";
    title.textContent = summary.source_file || "Uploaded PDF";
    section.appendChild(title);

    if (summary.error) {
      const error = document.createElement("p");
      error.className = "summary-error";
      error.textContent = summary.error;
      section.appendChild(error);
    } else {
      const list = document.createElement("ul");
      list.className = "summary-list";
      (summary.summary_points || []).forEach((point) => {
        const item = document.createElement("li");
        item.textContent = point;
        list.appendChild(item);
      });
      section.appendChild(list);
    }

    summaryPanel.appendChild(section);
  });

  summaryPlaceholder.hidden = true;
  summaryPanel.hidden = false;
}

async function summarizeSelectedFiles(requestId) {
  setSummaryLoading();

  const summaries = await Promise.all(selectedFiles.map(async (file) => {
    const payload = new FormData();
    payload.append("file", file);

    try {
      const response = await fetch("/summarize", { method: "POST", body: payload });
      if (!response.ok) {
        let detail = `Summary failed with status ${response.status}.`;
        try {
          const err = await response.json();
          detail = err.detail || detail;
        } catch {
          detail = await response.text();
        }
        throw new Error(detail);
      }
      return await response.json();
    } catch (error) {
      return {
        source_file: file.name,
        summary_points: [],
        error: error.message || "Summary generation failed.",
      };
    }
  }));

  if (requestId === summaryRequestId) {
    renderSummaryDashboard(summaries);
  }
}

// ─── Pagination ───────────────────────────────────────────────────────────────
// (pagination controls removed — single record view)

// ─── Copy button — removed ────────────────────────────────────────────────────

// ─── Form submission ──────────────────────────────────────────────────────────
extractForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  resultForm.hidden = true;
  Progress.reset();
  resetSummaryDashboard();

  const formData   = new FormData(extractForm);
  const attributes = String(formData.get("attributes") || "").trim();

  // Use our tracked selectedFiles array (handles both input and drop)
  if (!selectedFiles.length) {
    setMessage("Upload at least one PDF file.", "error");
    return;
  }
  if (!attributes) {
    setMessage("Enter at least one attribute to extract.", "error");
    return;
  }

  // Build fresh FormData using selectedFiles so drag-and-drop files are included
  const payload = new FormData();
  selectedFiles.forEach((f) => payload.append("files", f));
  payload.append("attributes", attributes);
  payload.append("output_format", "json");   // always JSON (toggle removed)

  setBusy(true);
  Progress.start(25000); // estimate 25 s; bar self-adjusts
  setMessage("Processing uploaded PDFs. This may take a moment for scanned documents.");
  summaryRequestId += 1;
  summarizeSelectedFiles(summaryRequestId);

  // Create object URLs for the uploaded files so citation modal can load them later.
  // We store a map { filename → objectURL }. We only need the first file for now
  // (multi-file support can extend this).
  const pdfObjectUrls = {};
  selectedFiles.forEach((f) => {
    pdfObjectUrls[f.name] = URL.createObjectURL(f);
  });

  try {
    const response = await fetch("/extract", { method: "POST", body: payload });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}.`;
      try {
        const err = await response.json();
        detail = err.detail || detail;
      } catch {
        detail = await response.text();
      }
      throw new Error(detail);
    }

    const data    = await response.json();
    const records = Array.isArray(data)
      ? data
      : Array.isArray(data.records)
        ? data.records
        : [data];

    // Attach the object URL of the source PDF to each record so the citation
    // modal can load it. Each record may carry a source_file filename.
    records.forEach((rec) => {
      const srcName = rec.source_file;
      if (srcName && pdfObjectUrls[srcName]) {
        rec._pdfUrl = pdfObjectUrls[srcName];
      } else {
        // Fallback: first file's URL
        rec._pdfUrl = Object.values(pdfObjectUrls)[0] ?? null;
      }
    });

    Progress.done();
    showResultPanel(records, records[0]?._pdfUrl ?? null);

    // Brief success state on the button
    submitButton.classList.add("btn--success");
    btnLabel.textContent = "✓ Done";
    setTimeout(() => {
      submitButton.classList.remove("btn--success");
      btnLabel.textContent = "Extract Data";
    }, 2000);
    setMessage("");

  } catch (error) {
    Progress.error();
    resultForm.hidden = true;
    setMessage(error.message || "Extraction failed.", "error");
    setStatus("error", "Service Unavailable");
  } finally {
    setBusy(false);
  }
});

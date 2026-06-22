// ─── DOM references ──────────────────────────────────────────────────────────
const extractForm       = document.querySelector("#extractForm");
const submitButton      = document.querySelector("#submitButton");
const btnLabel          = document.querySelector("#btnLabel");
const btnSpinner        = document.querySelector("#btnSpinner");
const message           = document.querySelector("#message");
const statusPill        = document.querySelector("#statusPill");
const statusText        = statusPill.querySelector(".status-text");
const copyButton        = document.querySelector("#copyButton");
const resultPlaceholder = document.querySelector("#resultPlaceholder");
const resultForm        = document.querySelector("#resultForm");
const prevRecord        = document.querySelector("#prevRecord");
const nextRecord        = document.querySelector("#nextRecord");
const recordCounter     = document.querySelector("#recordCounter");
const dropzone          = document.querySelector("#dropzone");
const fileInput         = document.querySelector("#files");
const fileList          = document.querySelector("#fileList");
const fileSuccessPanel  = document.querySelector("#fileSuccessPanel");
const fileSuccessLabel  = document.querySelector("#fileSuccessLabel");
const clearFilesBtn     = document.querySelector("#clearFilesBtn");

// ─── State ───────────────────────────────────────────────────────────────────
let allRecords   = [];
let currentIndex = 0;

// Tracks the current FileList-compatible array for submission
let selectedFiles = [];

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
  // Reset the native file input so the same file can be re-added
  fileInput.value = "";
  selectedFiles   = [];
  applyFileSelection([]);
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

// ─── Inline autocomplete (Tab-to-accept) ─────────────────────────────────────
/**
 * Creates an autocomplete wrapper for one extracted field.
 *
 * Ghost visibility fix:
 *   - Ghost starts fully visible (real input has transparent background).
 *   - Once the user types, the real input gets a near-opaque background via
 *     the `has-value` class so typed characters clearly overlay the ghost tail.
 *   - Tab accepts the full suggestion; ghost clears.
 *
 * @param {string} name       – field name
 * @param {string} suggestion – full value extracted from the PDF
 * @returns {HTMLElement}
 */
function createAutocompleteField(name, suggestion) {
  const wrapper = document.createElement("div");
  wrapper.className = "autocomplete-wrapper";

  // Real input
  const input = document.createElement("input");
  input.type         = "text";
  input.name         = name;
  input.id           = `field-${name}`;
  input.className    = "autocomplete-input";
  input.value        = "";
  input.autocomplete = "off";
  input.spellcheck   = false;
  input.setAttribute("aria-label", name.replace(/_/g, " "));
  input.setAttribute("aria-autocomplete", "inline");

  // Ghost — full suggestion, visible immediately
  const ghost = document.createElement("input");
  ghost.type      = "text";
  ghost.className = "autocomplete-ghost";
  ghost.tabIndex  = -1;
  ghost.setAttribute("aria-hidden", "true");
  ghost.readOnly  = true;
  ghost.value     = suggestion;

  // As user types: update ghost tail, add has-value class so typed text
  // has an opaque backing and the remaining suggestion peeks behind it.
  input.addEventListener("input", () => {
    const typed = input.value;
    if (typed.length > 0) {
      input.classList.add("has-value");
      if (suggestion.toLowerCase().startsWith(typed.toLowerCase())) {
        ghost.value = typed + suggestion.slice(typed.length);
      } else {
        ghost.value = "";
      }
    } else {
      input.classList.remove("has-value");
      ghost.value = suggestion;  // restore full ghost when cleared
    }
  });

  // Tab → accept full suggestion, advance focus
  input.addEventListener("keydown", (e) => {
    if (e.key === "Tab" && ghost.value) {
      e.preventDefault();
      input.value = ghost.value;
      input.classList.add("has-value");
      ghost.value = "";
      const inputs = Array.from(resultForm.querySelectorAll(".autocomplete-input"));
      const idx    = inputs.indexOf(input);
      if (idx !== -1 && idx + 1 < inputs.length) inputs[idx + 1].focus();
    }
  });

  // Restore full ghost when user empties the field and tabs away
  input.addEventListener("blur", () => {
    if (!input.value) {
      input.classList.remove("has-value");
      ghost.value = suggestion;
    }
  });

  wrapper.appendChild(ghost);
  wrapper.appendChild(input);
  return wrapper;
}

// ─── Result form renderer ─────────────────────────────────────────────────────
function renderRecord(record) {
  resultForm.innerHTML = "";
  Object.entries(record).forEach(([key, value]) => {
    if (key === "source_file") return;   // remove source file field
    const group = document.createElement("div");
    group.className = "result-field-group";

    const label = document.createElement("label");
    label.htmlFor     = `field-${key}`;
    label.textContent = key.replace(/_/g, " ");

    group.appendChild(label);
    group.appendChild(createAutocompleteField(key, String(value ?? "")));
    resultForm.appendChild(group);
  });
}

function showRecord(index) {
  if (!allRecords.length) return;
  currentIndex              = index;
  renderRecord(allRecords[index]);
  recordCounter.textContent = `${index + 1} / ${allRecords.length}`;
}

function showResultPanel(records) {
  allRecords   = records;
  currentIndex = 0;

  resultPlaceholder.hidden = true;
  resultForm.hidden        = false;
  copyButton.disabled      = false;

  const many = records.length > 1;
  prevRecord.hidden    = !many;
  nextRecord.hidden    = !many;
  recordCounter.hidden = !many;

  showRecord(0);
  setStatus("ready", "System Operational");
}

// ─── Pagination ───────────────────────────────────────────────────────────────
prevRecord.addEventListener("click", () => {
  if (currentIndex > 0) showRecord(currentIndex - 1);
});
nextRecord.addEventListener("click", () => {
  if (currentIndex < allRecords.length - 1) showRecord(currentIndex + 1);
});

// ─── Copy button ─────────────────────────────────────────────────────────────
copyButton.addEventListener("click", async () => {
  const fd = new FormData(resultForm);
  allRecords[currentIndex] = { ...allRecords[currentIndex], ...Object.fromEntries(fd.entries()) };
  try {
    await navigator.clipboard.writeText(JSON.stringify(allRecords, null, 2));
    setMessage("JSON copied to clipboard.", "success");
  } catch {
    setMessage("Could not copy JSON from this browser.", "error");
  }
});

// ─── Form submission ──────────────────────────────────────────────────────────
extractForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  copyButton.disabled      = true;
  resultForm.hidden        = true;
  resultPlaceholder.hidden = false;

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
  setMessage("Processing uploaded PDFs. This may take a moment for scanned documents.");

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

    showResultPanel(records);
    setMessage("Extraction completed. Review and edit fields below.", "success");

  } catch (error) {
    resultPlaceholder.hidden = false;
    resultForm.hidden        = true;
    setMessage(error.message || "Extraction failed.", "error");
    setStatus("error", "Service Unavailable");
  } finally {
    setBusy(false);
  }
});

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
const pdfCanvasWrap  = document.querySelector("#pdfCanvasWrap");
const pdfViewerWrap  = document.querySelector("#pdfViewerWrap");
const pdfHighlight   = document.querySelector("#pdfHighlight");
const pdfTooltip     = document.querySelector("#pdfTooltip");
const pdfErrorMsg    = document.querySelector("#pdfErrorMsg");
const pdfFallbackContent = document.querySelector("#pdfFallbackContent");
const pdfFallbackLabel   = document.querySelector("#pdfFallbackLabel");
const pdfFallbackValue   = document.querySelector("#pdfFallbackValue");
const pdfFallbackPage    = document.querySelector("#pdfFallbackPage");
const pdfTryAgainBtn     = document.querySelector("#pdfTryAgainBtn");
const pdfDownloadBtn     = document.querySelector("#pdfDownloadBtn");
const pdfFallbackCloseBtn = document.querySelector("#pdfFallbackCloseBtn");

// Document validity banner
const docValidityBanner = document.querySelector("#docValidityBanner");

// ─── State ───────────────────────────────────────────────────────────────────
let allRecords   = [];
let currentIndex = 0;
let summaryRequestId = 0;

// Tracks the current FileList-compatible array for submission
let selectedFiles = [];

// ─── Document Validity Banner ─────────────────────────────────────────────────
/**
 * Handles the document_validity object returned by the extraction API.
 *
 * Severity levels:
 *   "block"  — is_valid: false  → hide results, show amber advisory banner
 *   "notice" — is_valid: true + confidence: "low" → show inline soft notice
 *   "none"   — is_valid: true + confidence: "high"|"medium" → clear and hide
 *
 * Returns true if the caller should proceed to render results,
 * false if results must be suppressed (block case).
 */
const DocValidity = (() => {
  const FALLBACK_MSG =
    "We couldn't identify this as a Letter of Award (LOA), Completion Certificate (CC), " +
    "Provisional Completion Certificate (PCC), Financial Closure, Debarment Records, or " +
    "Debarment of Individuals document. Please verify the uploaded file and try again.";

  const TYPE_LABELS = {
    loa:                "Letter of Award (LOA)",
    "letter of award":  "Letter of Award (LOA)",
    pcc:                "Provisional Completion Certificate (PCC)",
    "provisional completion certificate": "Provisional Completion Certificate (PCC)",
    cc:                 "Completion Certificate (CC)",
    "completion certificate": "Completion Certificate (CC)",
    "financial closure": "Financial Closure",
    "debarment records": "Debarment Records",
    "debarment of individuals": "Debarment of Individuals",
    debarment:          "Debarment Document",
  };

  function _label(detectedType) {
    if (!detectedType) return "unknown document type";
    const normalized = String(detectedType).toLowerCase().trim();
    return TYPE_LABELS[normalized] || detectedType || "unknown document type";
  }

  function _clear() {
    docValidityBanner.hidden = true;
    docValidityBanner.className = "doc-validity-banner";
    docValidityBanner.innerHTML = "";
  }

  /**
   * Evaluates document_validity and updates the banner.
   * @param {object|null} validity - The document_validity object from the API.
   * @returns {boolean} true = render results, false = suppress results.
   */
  function evaluate(validity) {
    _clear();

    if (!validity) return true;   // no validity data — treat as valid

    const { is_valid, detected_type, confidence, message } = validity;

    // ── Case 1: Hard block ─────────────────────────────────────────────────
    if (!is_valid) {
      const msg = message || FALLBACK_MSG;
      docValidityBanner.className = "doc-validity-banner doc-validity-banner--block";
      docValidityBanner.innerHTML = `
        <div class="banner-header">
          <span class="banner-icon" aria-hidden="true">⚠️</span>
          <div class="banner-header-text">
            <p class="banner-title">Invalid Document Type Detected${detected_type ? ` (${detected_type})` : ''}. Extraction Halted.</p>
            <p class="banner-body">${_escHtml(msg)}</p>
          </div>
        </div>
        <div class="banner-actions">
          <button type="button" class="banner-action banner-action--primary" id="bannerUploadBtn">
            ↑ Upload Correct Document
          </button>
          <button type="button" class="banner-action banner-action--secondary" id="bannerForceExtractBtn">
            Force Extract Anyway
          </button>
        </div>
      `;
      docValidityBanner.hidden = false;

      // Wire the "Upload a different file" button to clear + focus the dropzone
      document.getElementById("bannerUploadBtn").addEventListener("click", () => {
        clearFilesBtn.click();
        dropzone.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(() => fileInput.click(), 300);
      });

      // Wire the "Force Extract Anyway" button to dismiss banner and show results
      document.getElementById("bannerForceExtractBtn").addEventListener("click", () => {
        _clear();
        // Re-trigger result rendering if results were suppressed
        if (resultForm.hidden) {
          resultForm.hidden = false;
          resultForm.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        // Also generate summary now since user chose to proceed
        summaryRequestId += 1;
        summarizeSelectedFiles(summaryRequestId);
      });

      return false;   // suppress results
    }

    // ── Case 2: Soft notice (low confidence) ──────────────────────────────
    if (is_valid && confidence === "low") {
      const typeLabel = _label(detected_type);
      docValidityBanner.className = "doc-validity-banner doc-validity-banner--notice";
      docValidityBanner.innerHTML = `
        <span class="banner-notice-icon" aria-hidden="true">ℹ️</span>
        <p class="banner-notice-text">
          This appears to be a <strong>${_escHtml(typeLabel)}</strong>, but please review the extracted fields for accuracy.
        </p>
      `;
      docValidityBanner.hidden = false;
      return true;    // render results with notice
    }

    // ── Case 3: High/medium confidence — no banner ────────────────────────
    return true;
  }

  function reset() { _clear(); }

  function _escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  return { evaluate, reset };
})();

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
const PdfModal = (() => {
  let _pdfDoc         = null;
  let _fileUrl        = null;
  let _tooltipTimer   = null;
  let _lastSourceData = null;
  let _lastFieldName  = "";

  if (typeof pdfjsLib !== "undefined") {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  }

  function _show() { pdfModal.hidden = false; document.body.style.overflow = "hidden"; }
  function _hide() { pdfModal.hidden = true;  document.body.style.overflow = ""; _cleanup(); }

  function _cleanup() {
    clearTimeout(_tooltipTimer);
    pdfTooltip.hidden         = true;
    pdfFallbackContent.hidden = true;
    pdfViewerWrap.hidden      = false;
    pdfCanvas.hidden          = false;
    pdfPageInfo.textContent   = "";
    pdfCanvasWrap.querySelectorAll(".pdf-highlight-box, .pdf-bbox-overlay").forEach(el => el.remove());
    pdfCanvas.getContext("2d")?.clearRect(0, 0, pdfCanvas.width, pdfCanvas.height);
    // Reset modal scroll position
    const scrollContainer = pdfModal.querySelector(".pdf-modal-body");
    if (scrollContainer) scrollContainer.scrollTop = 0;
  }

  // ── Render a PDF page ─────────────────────────────────────────────────────
  async function _renderPage(pageNum) {
    if (!_pdfDoc) return null;
    try {
      const page      = await _pdfDoc.getPage(pageNum);
      const available = pdfViewerWrap.clientWidth || 800;
      const scale     = Math.min(available / page.getViewport({ scale: 1 }).width * 0.92, 1.6);
      const viewport  = page.getViewport({ scale });
      pdfCanvas.width  = viewport.width;
      pdfCanvas.height = viewport.height;
      await page.render({ canvasContext: pdfCanvas.getContext("2d"), viewport }).promise;
      pdfPageInfo.textContent = `Page ${pageNum} of ${_pdfDoc.numPages}`;
      return { page, viewport };
    } catch (err) {
      console.error("[Citation] render failed:", err);
      return null;
    }
  }

  // ── Paint yellow highlight directly onto the canvas ───────────────────────
  // boxes: array of { left, top, width, height } in canvas pixels
  function _paintHighlight(boxes) {
    const ctx = pdfCanvas.getContext("2d");
    if (!ctx || !boxes.length) return;
    ctx.save();
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = "rgba(255, 215, 0, 0.55)";
    const PAD = 3;
    boxes.forEach(({ left, top, width, height }) => {
      ctx.fillRect(
        Math.max(left  - PAD, 0),
        Math.max(top   - PAD, 0),
        width  + PAD * 2,
        height + PAD * 2,
      );
    });
    ctx.restore();
  }

  // ── Show tooltip above the first highlighted box ──────────────────────────
  function _showTooltip(boxes) {
    if (!boxes.length) return;
    const b  = boxes[0];
    const cr = pdfCanvas.getBoundingClientRect();
    const wr = pdfCanvasWrap.getBoundingClientRect();
    pdfTooltip.textContent     = "Source text highlighted";
    pdfTooltip.style.left      = `${(cr.left - wr.left) + b.left + b.width / 2}px`;
    pdfTooltip.style.top       = `${Math.max((cr.top - wr.top) + b.top - 36, 4)}px`;
    pdfTooltip.style.transform = "translateX(-50%)";
    pdfTooltip.hidden = false;
    clearTimeout(_tooltipTimer);
    _tooltipTimer = setTimeout(() => { pdfTooltip.hidden = true; }, 5000);
    _scrollToHighlight(boxes);
  }

  // ── Smooth-scroll the modal body so the highlighted region is centred ─────
  // Accepts either a DOM element (the bbox overlay div) or a canvas-pixel
  // boxes array for the legacy canvas-paint path.
  function _scrollToHighlight(target) {
    // If we received an Element (the overlay div), use scrollIntoView directly.
    if (target instanceof Element) {
      requestAnimationFrame(() => {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      return;
    }

    // Legacy path: boxes array from canvas-paint strategy.
    const boxes = Array.isArray(target) ? target : [];
    if (!boxes.length) return;

    requestAnimationFrame(() => {
      const minTop    = Math.min(...boxes.map(b => b.top));
      const maxBottom = Math.max(...boxes.map(b => b.top + b.height));
      const midY      = (minTop + maxBottom) / 2;

      const scrollContainer = pdfModal.querySelector(".pdf-modal-body");
      if (!scrollContainer) {
        pdfCanvas.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }

      // Walk up offsetParent chain from canvas to the scroll container
      let canvasOffsetTop = 0;
      let el = pdfCanvas;
      while (el && el !== scrollContainer) {
        canvasOffsetTop += el.offsetTop;
        el = el.offsetParent;
      }

      const highlightAbsY = canvasOffsetTop + midY;
      const targetScrollTop = highlightAbsY - scrollContainer.clientHeight / 2;
      scrollContainer.scrollTo({ top: Math.max(targetScrollTop, 0), behavior: "smooth" });
    });
  }

  // ── Strategy A+: bbox overlay div ────────────────────────────────────────
  // The backend bbox comes from Tesseract, which operates on the rasterised
  // page image.  _pixels_to_points divides by zoom but preserves the
  // top-down y-axis (y=0 at top of page, same as the canvas).
  //
  // To normalise to 0-1 we therefore divide by the CANVAS pixel dimensions,
  // then multiply back out by zoom — which simplifies to dividing the
  // point-space coords by (canvasPx / zoom):
  //
  //   nx = x0_pt / (canvas.width  / zoom)
  //   ny = y0_pt / (canvas.height / zoom)
  //
  // canvasDim / zoom == naturalViewport dimension (in pt), so the formula
  // is equivalent to x0_pt / naturalWidth — but we pass the canvas and zoom
  // explicitly to make the intent clear and avoid confusion with the PDF
  // y-flip that applies to native (non-scanned) PDFs.
  function _injectBboxOverlay(sourceData, canvasWidth, canvasHeight, zoom) {
    // Remove any previous overlay
    pdfCanvasWrap.querySelectorAll(".pdf-bbox-overlay").forEach(el => el.remove());

    const rects = sourceData.bbox_lines || (sourceData.bbox ? [sourceData.bbox] : null);
    if (!rects || !rects.length || !canvasWidth || !canvasHeight) return null;

    // Natural page dimensions in the same point space as the bbox
    const natW = canvasWidth  / zoom;
    const natH = canvasHeight / zoom;

    // Union of all rects
    const x0 = Math.min(...rects.map(r => r[0]));
    const y0 = Math.min(...rects.map(r => r[1]));
    const x1 = Math.max(...rects.map(r => r[2]));
    const y1 = Math.max(...rects.map(r => r[3]));

    // Normalise to 0-1, clamped to page bounds
    const nx = Math.max(0, Math.min(x0 / natW, 1));
    const ny = Math.max(0, Math.min(y0 / natH, 1));
    const nw = Math.max(0, Math.min((x1 - x0) / natW, 1 - nx));
    const nh = Math.max(0, Math.min((y1 - y0) / natH, 1 - ny));

    // Reject degenerate boxes
    if (nw < 0.001 || nh < 0.001) return null;

    const overlay = document.createElement("div");
    overlay.className    = "pdf-bbox-overlay";
    overlay.style.left   = `${nx * 100}%`;
    overlay.style.top    = `${ny * 100}%`;
    overlay.style.width  = `${nw * 100}%`;
    overlay.style.height = `${nh * 100}%`;
    overlay.setAttribute("aria-hidden", "true");

    pdfCanvasWrap.appendChild(overlay);
    return overlay;
  }

  // ── Strategy A: use pre-computed PDF-point bbox from the backend ──────────
  // sourceData.bbox       = [x0, y0, x1, y1]  in PDF points (72 pt = 1 inch)
  // sourceData.bbox_lines = [[x0,y0,x1,y1],…] one per line, same units
  //
  // PDF.js viewport.transform = [scaleX, 0, 0, -scaleY, offsetX, offsetY]
  // To convert a PDF point (px, py) → canvas pixel (cx, cy):
  //   cx = px * scaleX + offsetX
  //   cy = py * (-scaleY) + offsetY   (y-axis is flipped in PDF coordinates)
  function _bboxToCanvasBoxes(sourceData, viewport) {
    const rects = sourceData.bbox_lines || (sourceData.bbox ? [sourceData.bbox] : null);
    if (!rects || !rects.length) return null;

    const [scaleX, , , scaleY, offX, offY] = viewport.transform;
    // scaleY is negative in PDF.js (PDF y grows up, canvas y grows down)

    return rects.map(([x0, y0, x1, y1]) => {
      // Top-left corner in canvas space
      const cx0 = x0 * scaleX + offX;
      const cy0 = y0 * scaleY + offY;   // scaleY is negative, offY accounts for flip
      // Bottom-right corner
      const cx1 = x1 * scaleX + offX;
      const cy1 = y1 * scaleY + offY;

      // Normalise so left/top are always the smaller values
      const left   = Math.min(cx0, cx1);
      const top    = Math.min(cy0, cy1);
      const width  = Math.abs(cx1 - cx0);
      const height = Math.abs(cy1 - cy0);
      return { left, top, width, height };
    });
  }

  // ── Strategy B: text-layer search (fallback for native-text PDFs) ─────────
  function _norm(t) {
    return String(t || "").toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, " ").replace(/\s+/g, " ").trim();
  }

  function _itemBox(item, viewport) {
    // m = [ scaleX, skewY, skewX, scaleY, translateX, translateY ]
    // In PDF.js the transform is already in canvas-pixel space after applying
    // viewport.transform, so m[4]/m[5] are the bottom-left corner in canvas px.
    const m      = pdfjsLib.Util.transform(viewport.transform, item.transform);
    // scaleX in the composed matrix gives us the actual rendered scale
    const scaleX = Math.sqrt(m[0] * m[0] + m[1] * m[1]);
    const height = Math.max(Math.abs(m[3]), 6);
    return {
      left:   m[4],
      top:    m[5] - height,
      width:  Math.max(item.width * scaleX, 6),
      height,
    };
  }

  function _findItems(items, snippet) {
    const target = _norm(snippet);
    if (!target || target === "null" || target.length < 2) return [];

    // Pass 1 — exact sliding window
    for (let s = 0; s < items.length; s++) {
      let buf = "";
      for (let e = s; e < items.length; e++) {
        buf += (buf ? " " : "") + (items[e].str || "");
        if (_norm(buf).includes(target)) return items.slice(s, e + 1);
        if (_norm(buf).length > target.length + 80) break;
      }
    }

    // Pass 2 — fuzzy word overlap (multi-word only, ≥70%)
    const words = target.split(" ").filter(w => w.length >= 2);
    if (words.length < 2) return [];
    let best = null;
    for (let s = 0; s < items.length; s++) {
      let buf = "";
      for (let e = s; e < Math.min(items.length, s + 14); e++) {
        buf += (buf ? " " : "") + (items[e].str || "");
        const score = words.filter(w => _norm(buf).includes(w)).length / words.length;
        if (!best || score > best.score) best = { s, e, score };
        if (score === 1) break;
      }
    }
    return best?.score >= 0.7 ? items.slice(best.s, best.e + 1) : [];
  }

  async function _tryHighlightViaTextLayer(page, viewport, snippet) {
    if (!snippet || snippet === "Null") return false;
    try {
      const tc    = await page.getTextContent();
      const items = (tc.items || []).filter(it => String(it.str || "").trim());
      if (!items.length) return false;
      const matched = _findItems(items, snippet);
      if (!matched.length) {
        console.debug("[Citation] text-layer: no match for snippet:", snippet?.slice(0, 60));
        return false;
      }
      const boxes = matched.map(it => _itemBox(it, viewport));
      _paintHighlight(boxes);
      _showTooltip(boxes);
      return true;
    } catch (err) {
      console.warn("[Citation] text-layer search failed:", err);
      return false;
    }
  }

  // ── Source banner removed — highlight is rendered directly on the canvas ──
  // (function stub kept to avoid call-site changes in open())
  function _showBanner(_snippet, _fieldName) { /* intentionally empty */ }

  function _esc(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function _showFallback(msg, sourceData, fieldName) {
    pdfViewerWrap.hidden = true; pdfCanvas.hidden = true; pdfTooltip.hidden = true;
    pdfErrorMsg.textContent      = `${msg} Source information:`;
    pdfFallbackLabel.textContent = (fieldName || "").replace(/_/g, " ");
    pdfFallbackValue.textContent = sourceData?.text || sourceData?.value || "Null";
    pdfFallbackPage.textContent  = "See source text above";
    pdfFallbackContent.hidden    = false;
  }

  // ── Public open() ─────────────────────────────────────────────────────────
  async function open(fileUrl, sourceData, fieldName) {
    _cleanup();
    pdfCanvas.hidden           = false;
    pdfModalTitle.textContent  = fieldName
      ? `Source — ${fieldName.replace(/_/g, " ")}` : "Source Document";
    _fileUrl        = fileUrl;
    _lastSourceData = sourceData;
    _lastFieldName  = fieldName;
    _show();

    if (typeof pdfjsLib === "undefined") {
      _showFallback("PDF.js not loaded.", sourceData, fieldName); return;
    }

    const snippet = sourceData?.text || sourceData?.value || "";
    _showBanner(snippet, fieldName);

    try {
      pdfViewerWrap.hidden = false; pdfFallbackContent.hidden = true;
      _pdfDoc = await pdfjsLib.getDocument(fileUrl).promise;

      // pageNumber from backend is 0-indexed sentinel; treat 0 as "page 1".
      const rawPage    = Number(sourceData?.pageNumber) || 0;
      const targetPage = rawPage >= 1 ? rawPage : 1;
      const clampedPage = Math.min(Math.max(targetPage, 1), _pdfDoc.numPages);

      const rendered = await _renderPage(clampedPage);
      if (!rendered) { _showFallback("Page render failed.", sourceData, fieldName); return; }

      const { page, viewport } = rendered;
      let highlighted = false;

      // ── Strategy A: bbox overlay div (scanned PDFs — Tesseract top-down coords) ──
      // Pass the rendered canvas pixel dimensions and the backend zoom factor so
      // _injectBboxOverlay can convert Tesseract "image points" → 0-1 percentages
      // without applying the PDF y-flip (which only applies to native vector PDFs).
      if (sourceData?.bbox || sourceData?.bbox_lines) {
        // zoom = PdfRenderer.zoom (default 2.0).  If the field doesn't carry it
        // we fall back to the ratio canvas / naturalViewport, which is the same value.
        const naturalViewport = page.getViewport({ scale: 1 });
        const derivedZoom = pdfCanvas.width / naturalViewport.width;

        const overlayEl = _injectBboxOverlay(
          sourceData,
          pdfCanvas.width,
          pdfCanvas.height,
          derivedZoom,
        );

        if (overlayEl) {
          // Position the tooltip above the overlay using its rendered rect
          requestAnimationFrame(() => {
            const or = overlayEl.getBoundingClientRect();
            const wr = pdfCanvasWrap.getBoundingClientRect();
            pdfTooltip.textContent     = "Source text highlighted";
            pdfTooltip.style.left      = `${(or.left - wr.left) + or.width / 2}px`;
            pdfTooltip.style.top       = `${Math.max((or.top - wr.top) - 36, 4)}px`;
            pdfTooltip.style.transform = "translateX(-50%)";
            pdfTooltip.hidden = false;
            clearTimeout(_tooltipTimer);
            _tooltipTimer = setTimeout(() => { pdfTooltip.hidden = true; }, 5000);
          });

          _scrollToHighlight(overlayEl);
          highlighted = true;
          console.debug(`[Citation] bbox overlay at ${overlayEl.style.left},${overlayEl.style.top} for "${fieldName}"`);
        }
      }

      // ── Strategy B: text-layer fallback (native-text PDFs, no bbox) ──────
      if (!highlighted && snippet && snippet !== "Null") {
        highlighted = await _tryHighlightViaTextLayer(page, viewport, snippet);
        if (highlighted) {
          console.debug(`[Citation] highlighted via text-layer for "${fieldName}"`);
        }
      }

      pdfPageInfo.textContent = highlighted
        ? `Page ${clampedPage} — text highlighted in yellow`
        : `Page ${clampedPage}`;

      // Fallback: if nothing was highlighted, scroll to the top of the canvas
      // so the user at least lands on the correct page.
      if (!highlighted) {
        const scrollContainer = pdfModal.querySelector(".pdf-modal-body");
        if (scrollContainer) {
          setTimeout(() => scrollContainer.scrollTo({ top: 0, behavior: "smooth" }), 120);
        }
      }

    } catch (err) {
      console.error("[Citation] open() error:", err);
      _showFallback("Unable to load PDF.", sourceData, fieldName);
    }
  }

  pdfTryAgainBtn.addEventListener("click",      () => { if (_fileUrl) open(_fileUrl, _lastSourceData, _lastFieldName); });
  pdfDownloadBtn.addEventListener("click",      () => { if (!_fileUrl) return; const a=document.createElement("a"); a.href=_fileUrl; a.download="source.pdf"; a.click(); });
  pdfModalClose.addEventListener("click",       _hide);
  pdfFallbackCloseBtn.addEventListener("click", _hide);
  pdfModal.addEventListener("click",            e => { if (e.target === pdfModal) _hide(); });
  document.addEventListener("keydown",          e => { if (e.key === "Escape" && !pdfModal.hidden) _hide(); });

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
  citBtn.textContent = "📄";
  citBtn.title       = source ? "View source in PDF" : "Open PDF";
  if (!source) citBtn.dataset.noSource = "true";
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
    // Pass the full source object so PdfModal gets bbox / bbox_lines too.
    PdfModal.open(
      fileUrl,
      {
        pageNumber: source?.pageNumber ?? 0,
        text:       source?.text       || suggestion || "Null",
        value:      suggestion         || "Null",
        bbox:       source?.bbox       ?? null,
        bbox_lines: source?.bbox_lines ?? null,
      },
      name,
    );
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

    // Pull per-field citation source if API returned source metadata.
    const source = record.source_meta?.[key] ?? record.sources?.[key] ?? record.source?.[key] ?? null;
    group.appendChild(createAutocompleteField(key, String(value ?? ""), group, source));
    resultForm.appendChild(group);
  });
}

function showRecord(index) {
  if (!allRecords.length) return;
  currentIndex = index;
  renderRecord(allRecords[index], allRecords[index]?._pdfUrl ?? resultForm.dataset.pdfUrl);
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
  DocValidity.reset();
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
  setMessage("Validating document type and processing PDFs...");

  // Create object URLs for the uploaded files so citation modal can load them later.
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
    console.log('[DEBUG] API Response:', data);
    
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

    // ── PRE-RENDER HARD GATE: Document Type Validation ────────────────────
    // Extraction has completed. Check if document is valid BEFORE rendering
    // results or generating summary.
    const validity = data.document_validity ?? null;
    console.log('[DEBUG] Document Validity:', validity);
    
    // Store records globally so "Force Extract Anyway" can access them
    allRecords   = records;
    currentIndex = 0;

    const shouldRenderResults = DocValidity.evaluate(validity);
    console.log('[DEBUG] Should Render Results:', shouldRenderResults);

    if (!shouldRenderResults) {
      // ❌ INVALID DOCUMENT DETECTED
      // Results suppressed, warning banner shown, NO SUMMARY GENERATED
      resultForm.hidden = true;
      resetSummaryDashboard();  // Ensure summary stays empty
      setStatus("ready", "System Operational");
      setMessage("");
      return;  // HARD STOP: Exit without rendering results or summary
    }

    // ✅ DOCUMENT VALID - Proceed with results + summary
    showResultPanel(records, records[0]?._pdfUrl ?? null);

    // NOW generate summary (only for valid documents)
    summaryRequestId += 1;
    summarizeSelectedFiles(summaryRequestId);

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

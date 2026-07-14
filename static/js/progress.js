/**
 * Progress indicator controller.
 * Manages the visibility and status text of the #progress-indicator element.
 *
 * Matches the actual markup in templates/index.html:
 *   <div id="progress-indicator" style="display:none">
 *     <span class="progress-spinner"></span>
 *     <p data-i18n="progress-msg">Processing document…</p>
 *   </div>
 */

function _el() {
  return document.getElementById("progress-indicator");
}

function _messageEl() {
  const indicator = _el();
  return indicator ? indicator.querySelector("p") : null;
}

/**
 * Show the progress indicator with an initial message.
 * @param {string} message
 */
export function showProgress(message = "Processing…") {
  const indicator = _el();
  const msgEl = _messageEl();
  if (msgEl) msgEl.textContent = message;
  if (indicator) indicator.style.display = "flex";
}

/**
 * Update only the status text (without changing visibility).
 * @param {string} message
 */
export function updateProgress(message) {
  const msgEl = _messageEl();
  if (msgEl) msgEl.textContent = message;
}

/**
 * Hide the progress indicator.
 */
export function hideProgress() {
  const indicator = _el();
  if (indicator) indicator.style.display = "none";
}

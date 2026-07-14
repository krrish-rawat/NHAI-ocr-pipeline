/**
 * Client-side validation helpers.
 * All functions return null on success or an error string on failure.
 */

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

/**
 * Validate an uploaded file is a PDF and within the size limit.
 * @param {File} file
 * @returns {string|null} null if valid, error message if not
 */
export function validateFile(file) {
  if (!file) return "Please select a PDF file.";
  const name = file.name || "";
  const type = file.type || "";
  if (!name.toLowerCase().endsWith(".pdf") && type !== "application/pdf") {
    return `Unsupported file type: ${name || "unnamed"}. Only PDF files are supported.`;
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `File is too large. Maximum size is 25 MB.`;
  }
  return null;
}

/**
 * Validate the fields textarea contains at least one non-empty field name.
 * @param {string} fieldsText - raw textarea value
 * @returns {string|null} null if valid, error message if not
 */
export function validateFields(fieldsText) {
  if (!fieldsText || !fieldsText.trim()) {
    return "Enter at least one field name to extract.";
  }
  const parts = fieldsText
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length === 0) {
    return "Enter at least one field name to extract.";
  }
  return null;
}

/**
 * Split a comma/newline-separated fields string into an array of trimmed field names.
 * @param {string} fieldsText
 * @returns {string[]}
 */
export function splitFields(fieldsText) {
  return fieldsText
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

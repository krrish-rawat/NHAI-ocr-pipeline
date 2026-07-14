// Fetch wrappers for the NHAI extraction API.
// Throws on non-OK HTTP responses with the server's error message.

/**
 * POST a multipart form to /extract.
 * Returns { type: "json", data } for JSON responses or
 * { type: "csv", blob } for CSV responses.
 *
 * @param {FormData} formData
 * @returns {Promise<{type: "json", data: object}|{type: "csv", blob: Blob}>}
 * @throws {Error} on non-2xx responses
 */
export async function postExtract(formData) {
  const response = await fetch("/extract", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      detail = (await response.text()) || detail;
    }
    throw new Error(detail);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/csv")) {
    return { type: "csv", blob: await response.blob() };
  }
  return { type: "json", data: await response.json() };
}

/**
 * POST a multipart form to /classify.
 * Returns the JSON classification result.
 *
 * @param {FormData} formData
 * @returns {Promise<object>}
 * @throws {Error} on non-2xx responses
 */
export async function postClassify(formData) {
  const response = await fetch("/classify", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Classify failed (${response.status})`);
  }

  return response.json();
}

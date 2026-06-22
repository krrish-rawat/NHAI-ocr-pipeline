const form = document.querySelector("#extractForm");
const submitButton = document.querySelector("#submitButton");
const message = document.querySelector("#message");
const resultOutput = document.querySelector("#resultOutput");
const statusPill = document.querySelector("#statusPill");
const downloadLink = document.querySelector("#downloadLink");
const copyButton = document.querySelector("#copyButton");

let activeDownloadUrl = "";

function setMessage(text, type = "") {
  message.textContent = text;
  message.className = `message ${type}`.trim();
}

function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  submitButton.textContent = isBusy ? "Extracting..." : "Extract data";
  statusPill.textContent = isBusy ? "Running" : "Ready";
}

function clearDownload() {
  if (activeDownloadUrl) {
    URL.revokeObjectURL(activeDownloadUrl);
  }
  activeDownloadUrl = "";
  downloadLink.hidden = true;
  downloadLink.removeAttribute("href");
}

function getOutputFormat() {
  return new FormData(form).get("output_format") || "json";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearDownload();
  copyButton.disabled = true;

  const formData = new FormData(form);
  const files = formData.getAll("files").filter((file) => file && file.size > 0);
  const attributes = String(formData.get("attributes") || "").trim();
  const outputFormat = getOutputFormat();

  if (!files.length) {
    setMessage("Upload at least one PDF file.", "error");
    return;
  }

  if (!attributes) {
    setMessage("Enter at least one attribute to extract.", "error");
    return;
  }

  setBusy(true);
  setMessage("Processing uploaded PDFs. This can take a little time for scanned documents.");
  resultOutput.textContent = outputFormat === "json" ? "{}" : "CSV output will download when ready.";

  try {
    const response = await fetch("/extract", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}.`;
      try {
        const errorPayload = await response.json();
        detail = errorPayload.detail || detail;
      } catch {
        detail = await response.text();
      }
      throw new Error(detail);
    }

    if (outputFormat === "csv") {
      const csvText = await response.text();
      const blob = new Blob([csvText], { type: "text/csv" });
      activeDownloadUrl = URL.createObjectURL(blob);
      downloadLink.href = activeDownloadUrl;
      downloadLink.download = "extracted_records.csv";
      downloadLink.hidden = false;
      resultOutput.textContent = csvText;
      setMessage("CSV extraction completed.", "success");
      statusPill.textContent = "Complete";
      return;
    }

    const payload = await response.json();
    const formatted = JSON.stringify(payload, null, 2);
    const blob = new Blob([formatted], { type: "application/json" });
    activeDownloadUrl = URL.createObjectURL(blob);
    downloadLink.href = activeDownloadUrl;
    downloadLink.download = "extracted_records.json";
    downloadLink.hidden = false;
    resultOutput.textContent = formatted;
    copyButton.disabled = false;
    setMessage("JSON extraction completed.", "success");
    statusPill.textContent = "Complete";
  } catch (error) {
    resultOutput.textContent = "{}";
    setMessage(error.message || "Extraction failed.", "error");
    statusPill.textContent = "Failed";
  } finally {
    setBusy(false);
  }
});

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(resultOutput.textContent);
    setMessage("JSON copied to clipboard.", "success");
  } catch {
    setMessage("Could not copy JSON from this browser.", "error");
  }
});

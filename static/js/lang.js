// Bilingual EN/HI language toggle.
// All elements with data-i18n attributes get their textContent swapped.
// Keys below match the actual data-i18n attributes used in templates/index.html.

const STRINGS = {
  en: {
    "upload-heading": "Upload & Extract",
    "label-pdf-file": "PDF Document",
    "hint-pdf-file": "Accepted format: PDF | Max size: 25 MB",
    "label-fields": "Fields to Extract",
    "hint-fields": "Be specific — e.g. \"Agreement Date\" not just \"Date\". One field per line.",
    "extract": "Extract",
    "progress-msg": "Processing document…",
    "rejection-title": "Document type not recognised or not supported",
    "force-extract": "Force Extract Anyway",
    "results-heading": "Extracted Data",
    "col-field": "Field",
    "col-value": "Value",
    "col-confidence": "Confidence",
    "download-json": "Download JSON",
    "download-csv": "Download CSV",
    "footer-nhai-heading": "National Highways Authority of India",
    "footer-links-heading": "Quick Links",
    "footer-legal-heading": "Legal",
    "footer-disclaimer": "Disclaimer",
    "footer-rti": "RTI",
    "footer-contact": "Contact",
    "footer-copyright": "© 2025 NHAI. Content owned and maintained by NHAI.",
    "footer-credit": "Designed & Developed by NIC | Last Updated: 2025",
  },
  hi: {
    "upload-heading": "अपलोड करें और निकालें",
    "label-pdf-file": "पीडीएफ दस्तावेज़",
    "hint-pdf-file": "स्वीकृत प्रारूप: PDF | अधिकतम आकार: 25 MB",
    "label-fields": "निष्कर्षण फ़ील्ड",
    "hint-fields": "विशिष्ट रहें — जैसे \"Agreement Date\" न कि सिर्फ \"Date\"। प्रति पंक्ति एक फ़ील्ड।",
    "extract": "निकालें",
    "progress-msg": "दस्तावेज़ प्रसंस्करण जारी है…",
    "rejection-title": "दस्तावेज़ प्रकार मान्यता प्राप्त या समर्थित नहीं है",
    "force-extract": "फिर भी निकालें",
    "results-heading": "निकाला गया डेटा",
    "col-field": "फ़ील्ड",
    "col-value": "मूल्य",
    "col-confidence": "विश्वास",
    "download-json": "JSON डाउनलोड",
    "download-csv": "CSV डाउनलोड",
    "footer-nhai-heading": "राष्ट्रीय राजमार्ग प्राधिकरण",
    "footer-links-heading": "त्वरित लिंक",
    "footer-legal-heading": "कानूनी",
    "footer-disclaimer": "अस्वीकरण",
    "footer-rti": "आरटीआई",
    "footer-contact": "संपर्क करें",
    "footer-copyright": "© 2025 एनएचएआई। सामग्री एनएचएआई के स्वामित्व और रखरखाव में है।",
    "footer-credit": "एनआईसी द्वारा डिज़ाइन और विकसित | अंतिम अपडेट: 2025",
  },
};

let _currentLang = "en";

/**
 * Returns the currently active language code ("en" or "hi").
 * @returns {string}
 */
export function getCurrentLang() {
  return _currentLang;
}

/**
 * Apply a language to the page: updates all [data-i18n] elements and the
 * lang-toggle button, then sets document.documentElement.lang.
 * @param {"en"|"hi"} lang
 */
export function applyLanguage(lang) {
  _currentLang = lang;
  const t = STRINGS[lang] || STRINGS.en;

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (t[key] !== undefined) el.textContent = t[key];
  });

  // Toggle button shows the OTHER language as the action label
  const toggleBtn = document.getElementById("lang-toggle");
  if (toggleBtn) toggleBtn.textContent = lang === "en" ? "हिंदी" : "English";

  document.documentElement.lang = lang === "hi" ? "hi" : "en";
}

/**
 * Wire up the #lang-toggle button to flip between EN and HI on click.
 * Safe to call before DOMContentLoaded — it's a no-op if the element is absent.
 */
export function initLangToggle() {
  const btn = document.getElementById("lang-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    applyLanguage(_currentLang === "en" ? "hi" : "en");
  });
}

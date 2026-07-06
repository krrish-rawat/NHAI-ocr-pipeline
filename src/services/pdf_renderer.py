import io
import logging
import shutil

import fitz
from PIL import Image

logger = logging.getLogger(__name__)


# Pixel-variance threshold below which a page is considered blank.
# A pure-white page has variance 0; real content is well above 50.
_BLANK_PAGE_VARIANCE_THRESHOLD = 50.0

# JPEG quality for images sent to the vision model.
# 85 preserves all text sharpness while cutting payload ~60% vs PNG.
_JPEG_QUALITY = 85


class PdfRenderer:
    """Renders PDF pages to images for vision-model extraction."""

    def __init__(self, zoom: float = 2.0) -> None:
        self.zoom = zoom

    def _is_blank(self, image: Image.Image) -> bool:
        """Return True if the page contains no meaningful content."""
        import statistics
        gray = image.convert("L")
        pixels = list(gray.getdata())
        try:
            variance = statistics.variance(pixels)
        except statistics.StatisticsError:
            return False
        return variance < _BLANK_PAGE_VARIANCE_THRESHOLD

    def _to_jpeg(self, image: Image.Image) -> Image.Image:
        """Re-encode as JPEG to reduce bytes sent to the API."""
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        buf.seek(0)
        return Image.open(buf)

    def render_to_images(self, pdf_path: str) -> list[Image.Image]:
        doc = fitz.open(pdf_path)
        images: list[Image.Image] = []

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
                image = Image.open(io.BytesIO(pix.tobytes("png")))

                if self._is_blank(image):
                    continue                  # skip empty/cover pages

                images.append(self._to_jpeg(image))
        finally:
            doc.close()

        # Fallback: if every page was flagged blank, return all as JPEG
        # (avoids sending zero images to the model).
        if not images:
            doc2 = fitz.open(pdf_path)
            try:
                for page_num in range(len(doc2)):
                    page = doc2.load_page(page_num)
                    pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
                    image = Image.open(io.BytesIO(pix.tobytes("png")))
                    images.append(self._to_jpeg(image))
            finally:
                doc2.close()

        return images

    # ------------------------------------------------------------------
    # OCR extraction layer
    # ------------------------------------------------------------------

    @staticmethod
    def _check_tesseract() -> bool:
        """Return True if the tesseract binary is available on PATH.

        Logs a clear warning when it is missing so operators know what to
        install rather than seeing a cryptic TesseractNotFoundError later.
        """
        if shutil.which("tesseract") is None:
            logger.warning(
                "tesseract-ocr is not installed or not on PATH. "
                "OCR extraction will be skipped. "
                "Install it with: sudo apt install tesseract-ocr  "
                "(or brew install tesseract on macOS)."
            )
            return False
        return True

    def extract_words_from_image(
        self, image: Image.Image
    ) -> list[dict]:
        """Run Tesseract OCR on *image* and return word-level bounding boxes.

        Parameters
        ----------
        image:
            A PIL Image – typically one element from the list returned by
            :meth:`render_to_images`.  The image is converted to RGB before
            being handed to Tesseract so it works regardless of original mode.

        Returns
        -------
        list[dict]
            One entry per recognised word (confidence > 0, non-empty text)::

                {
                    "text":       str,   # the recognised word
                    "left":       int,   # x of top-left corner  (pixels)
                    "top":        int,   # y of top-left corner  (pixels)
                    "width":      int,   # bounding-box width    (pixels)
                    "height":     int,   # bounding-box height   (pixels)
                    "confidence": float, # Tesseract confidence  (0-100)
                }

            Returns an empty list when Tesseract is unavailable or no words
            are found.
        """
        if not self._check_tesseract():
            return []

        try:
            import pytesseract  # lazy import – optional dependency
        except ImportError:
            logger.warning(
                "pytesseract is not installed. "
                "Run: pip install pytesseract"
            )
            return []

        # Tesseract works best on RGB images.
        rgb_image = image.convert("RGB")

        # image_to_data returns a TSV-like structure; output_type=DICT is
        # the most convenient form for downstream consumers.
        data = pytesseract.image_to_data(
            rgb_image,
            output_type=pytesseract.Output.DICT,
        )

        words: list[dict] = []
        num_entries = len(data["text"])

        for i in range(num_entries):
            raw_text = data["text"][i]
            # Tesseract fills gaps with empty strings; skip them.
            if not raw_text or not raw_text.strip():
                continue

            conf = float(data["conf"][i])
            # conf == -1 means the entry is a block/paragraph/line delimiter,
            # not an actual word recognition result.
            if conf < 0:
                continue

            words.append(
                {
                    "text": raw_text.strip(),
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "confidence": conf,
                }
            )

        logger.debug(
            "OCR found %d words in image (size=%s).", len(words), image.size
        )
        return words

    def extract_words_from_pdf(
        self, pdf_path: str
    ) -> list[list[dict]]:
        """Convenience wrapper: render every page and OCR each one.

        Returns a list aligned with the images from :meth:`render_to_images`;
        index *i* holds the word list for page *i*.
        """
        images = self.render_to_images(pdf_path)
        return [self.extract_words_from_image(img) for img in images]

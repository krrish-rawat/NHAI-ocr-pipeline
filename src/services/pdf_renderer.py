import io

import fitz
from PIL import Image


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

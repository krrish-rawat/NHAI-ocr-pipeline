import io

import fitz
from PIL import Image


class PdfRenderer:
    """Renders PDF pages to images for vision-model extraction."""

    def __init__(self, zoom: float = 2.0) -> None:
        self.zoom = zoom

    def render_to_images(self, pdf_path: str) -> list[Image.Image]:
        doc = fitz.open(pdf_path)
        images: list[Image.Image] = []

        try:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                images.append(image)
        finally:
            doc.close()

        return images

"""
document_processor.py — PDF / image preprocessing utilities.

Provides:
  - pdf_to_base64(path)          — Render page 0 of a PDF at 300 DPI → base64 PNG
  - image_to_base64(path)        — Load an image file → base64 PNG
  - preprocess_image(base64_str) — Grayscale + contrast 1.5× + sharpen → base64 PNG
"""

import base64
import io
import logging

import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


def pdf_to_base64(path: str) -> str:
    """
    Render the first page of a PDF at 300 DPI and return a base64-encoded PNG string.

    Args:
        path: Filesystem path to the PDF file.

    Returns:
        Base64-encoded PNG image of page 0.
    """
    doc = fitz.open(path)
    page = doc.load_page(0)

    # 300 DPI → scale factor = 300 / 72 ≈ 4.1667
    zoom = 300 / 72
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)

    img_bytes = pixmap.tobytes("png")
    doc.close()

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    logger.info("PDF rendered — path=%s page=0 size=%d bytes", path, len(img_bytes))
    return b64


def image_to_base64(path: str) -> str:
    """
    Load an image file (PNG, JPG, etc.) and return a base64-encoded PNG string.

    Args:
        path: Filesystem path to the image file.

    Returns:
        Base64-encoded PNG image.
    """
    img = Image.open(path)
    # Ensure consistent RGB mode for downstream processing
    if img.mode != "RGB":
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()

    b64 = base64.b64encode(img_bytes).decode("utf-8")
    logger.info("Image loaded — path=%s size=%d bytes", path, len(img_bytes))
    return b64


def preprocess_image(base64_str: str) -> str:
    """
    Apply low-confidence fallback preprocessing to an image:
      1. Convert to grayscale
      2. Increase contrast by factor 1.5
      3. Apply mild sharpening (Pillow SHARPEN filter)

    Args:
        base64_str: Base64-encoded PNG image string.

    Returns:
        Base64-encoded PNG string of the preprocessed image.
    """
    # Decode
    raw = base64.b64decode(base64_str)
    img = Image.open(io.BytesIO(raw))

    # 1. Grayscale
    img = img.convert("L")

    # 2. Contrast enhancement (1.5×)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # 3. Sharpen
    img = img.filter(ImageFilter.SHARPEN)

    # Re-encode
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    processed_bytes = buffer.getvalue()

    b64 = base64.b64encode(processed_bytes).decode("utf-8")
    logger.info("Image preprocessed — grayscale + contrast 1.5x + sharpen")
    return b64

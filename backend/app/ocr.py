"""Screenshot validation and optional Tesseract OCR (roadmap §13).

The upload is validated by magic bytes, decoded size, and dimensions before
anything else happens. OCR itself is feature-flagged: when the Tesseract
binary is missing, /v1/health reports ocrReady=false and /v1/ocr returns 503,
and the mobile app hides the screenshot flow. Images are processed in memory;
nothing is written to disk by this module.
"""

import io
import shutil
from statistics import mean

from PIL import Image

from . import config
from .errors import ApiError

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def validate_image(data: bytes) -> str:
    """Return the mime type for a valid JPEG/PNG upload, else raise."""
    if len(data) > config.MAX_IMAGE_BYTES:
        raise ApiError(413, "file_too_large", "Screenshots must be 10 MB or smaller.")
    if data.startswith(JPEG_MAGIC):
        mime = "image/jpeg"
    elif data.startswith(PNG_MAGIC):
        mime = "image/png"
    else:
        raise ApiError(422, "invalid_image", "Only JPEG or PNG screenshots are supported.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
    except Exception:
        raise ApiError(422, "invalid_image", "This file could not be read as an image.")
    if width > config.MAX_IMAGE_DIMENSION or height > config.MAX_IMAGE_DIMENSION:
        raise ApiError(422, "invalid_image", "This image is too large to process.")
    if width < 8 or height < 8:
        raise ApiError(422, "invalid_image", "This image is too small to contain readable text.")
    return mime


def extract_text(data: bytes) -> tuple[str, float]:
    """Run Tesseract on an already-validated image. Returns (text, mean confidence 0..1)."""
    if not available():
        raise ApiError(503, "ocr_unavailable",
                       "Screenshot text extraction is not available on this server yet.")
    import pytesseract

    image = None
    try:
        image = Image.open(io.BytesIO(data)).convert("L")  # grayscale helps Tesseract
        text = pytesseract.image_to_string(image, lang="eng").strip()
        info = pytesseract.image_to_data(image, lang="eng", output_type=pytesseract.Output.DICT)
        confidences = [int(c) for c in info.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
        confidence = round(mean(confidences) / 100, 2) if confidences else 0.0
        return text, confidence
    finally:
        if image is not None:
            image.close()

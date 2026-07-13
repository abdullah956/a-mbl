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

from PIL import Image, ImageOps

from . import config
from .errors import ApiError

# Preprocessing thresholds (roadmap §13): stop trying variants once one reads
# this confidently, and only attempt rotations when a variant read something
# but read it poorly (so pure-noise uploads never pay for the extra passes).
GOOD_CONFIDENCE = 0.85
ROTATE_BELOW = 0.50
BINARIZE_THRESHOLD = 160
# Cap the working resolution so no single OCR pass scales with a full 6000px
# upload — bounds CPU per request regardless of the image the caller sends.
OCR_MAX_DIMENSION = 2200

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


def _read(image: Image.Image) -> tuple[str, float]:
    """One Tesseract pass. Returns (text, mean word confidence 0..1)."""
    import pytesseract

    text = pytesseract.image_to_string(image, lang="eng").strip()
    info = pytesseract.image_to_data(image, lang="eng", output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in info.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
    return text, (mean(confidences) / 100 if confidences else 0.0)


def extract_text(data: bytes) -> tuple[str, float]:
    """Run Tesseract over preprocessing variants of an already-validated image
    and return the best (text, mean confidence 0..1) — roadmap §13.

    Variants cover the common screenshot failure modes: plain grayscale,
    contrast-stretched (washed-out/low-contrast themes), inverted (dark-mode
    light-on-dark text), and binarized (busy backgrounds). If everything reads
    poorly, the best variant is retried at 90/180/270 degrees for rotated
    screenshots.
    """
    if not available():
        raise ApiError(503, "ocr_unavailable",
                       "Screenshot text extraction is not available on this server yet.")

    with Image.open(io.BytesIO(data)) as original:
        gray = original.convert("L")

    # Downscale large images before OCR: Tesseract cost grows with pixel count,
    # and text is still legible at this size. Bounds the work per pass so a
    # full-resolution upload cannot pin a CPU core.
    if max(gray.size) > OCR_MAX_DIMENSION:
        gray.thumbnail((OCR_MAX_DIMENSION, OCR_MAX_DIMENSION))

    variants = [
        gray,
        ImageOps.autocontrast(gray, cutoff=1),
        ImageOps.invert(gray),
        gray.point(lambda p: 255 if p > BINARIZE_THRESHOLD else 0),
    ]

    best_text, best_confidence, best_image = "", 0.0, gray
    for candidate in variants:
        text, confidence = _read(candidate)
        if confidence > best_confidence or (text and not best_text):
            best_text, best_confidence, best_image = text, confidence, candidate
        if best_text and best_confidence >= GOOD_CONFIDENCE:
            break

    # Only try rotations when a variant read SOMETHING but read it poorly (a
    # skewed screenshot). Pure noise reads nothing, so it never triggers the
    # extra passes — that path stays at the variant cost, not 14 passes.
    if best_text and best_confidence < ROTATE_BELOW:
        for angle in (90, 180, 270):
            text, confidence = _read(best_image.rotate(angle, expand=True))
            if text and confidence > best_confidence:
                best_text, best_confidence = text, confidence

    return best_text, round(best_confidence, 2)

"""Screenshot upload validation and the OCR feature flag (roadmap §13)."""

import pytest

from backend.app import config, ocr


def test_non_image_upload_rejected(client, register, auth):
    session = register("ocr@test.io")
    response = client.post("/v1/ocr", files={"file": ("notes.txt", b"just text", "text/plain")},
                           headers=auth(session))
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_image"


def test_spoofed_extension_rejected(client, register, auth):
    session = register("ocr@test.io")
    response = client.post("/v1/ocr",
                           files={"file": ("fake.png", b"GIF89a not really", "image/png")},
                           headers=auth(session))
    assert response.status_code == 422


def test_corrupt_image_with_valid_magic_rejected(client, register, auth):
    session = register("ocr@test.io")
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # PNG magic, garbage body
    response = client.post("/v1/ocr", files={"file": ("broken.png", data, "image/png")},
                           headers=auth(session))
    assert response.status_code == 422


def test_oversized_upload_rejected(client, register, auth):
    session = register("ocr@test.io")
    data = b"\xff\xd8\xff" + b"\x00" * config.MAX_IMAGE_BYTES
    response = client.post("/v1/ocr", files={"file": ("big.jpg", data, "image/jpeg")},
                           headers=auth(session))
    assert response.status_code == 413


def test_ocr_requires_auth(client, png_bytes):
    response = client.post("/v1/ocr", files={"file": ("shot.png", png_bytes(), "image/png")})
    assert response.status_code == 401


@pytest.mark.skipif(ocr.available(), reason="Tesseract installed; 503 path not reachable")
def test_valid_image_reports_ocr_unavailable_without_tesseract(client, register, auth, png_bytes):
    session = register("ocr@test.io")
    response = client.post("/v1/ocr", files={"file": ("shot.png", png_bytes(), "image/png")},
                           headers=auth(session))
    assert response.status_code == 503
    assert response.json()["code"] == "ocr_unavailable"


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_extracts_text_when_available(client, register, auth):
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (400, 120), "white")
    ImageDraw.Draw(image).text((20, 40), "HELLO WORLD", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    session = register("ocr@test.io")
    response = client.post("/v1/ocr",
                           files={"file": ("shot.png", buffer.getvalue(), "image/png")},
                           headers=auth(session))
    assert response.status_code == 200
    assert "text" in response.json()


def test_validate_image_accepts_real_png(png_bytes):
    assert ocr.validate_image(png_bytes()) == "image/png"


def _screenshot(background, fill, angle=0):
    """Synthesize a screenshot-like PNG with large readable text."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (640, 200), background)
    ImageDraw.Draw(image).text((30, 60), "HELLO WORLD",
                               fill=fill, font=ImageFont.load_default(48))
    if angle:
        image = image.rotate(angle, expand=True, fillcolor=background)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_reads_dark_mode_screenshots():
    text, confidence = ocr.extract_text(_screenshot("black", "white"))
    assert "HELLO" in text.upper()
    assert confidence > 0.5


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_reads_low_contrast_screenshots():
    text, _ = ocr.extract_text(_screenshot("white", (205, 205, 205)))
    assert "HELLO" in text.upper()


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_reads_rotated_screenshots():
    text, _ = ocr.extract_text(_screenshot("white", "black", angle=90))
    assert "HELLO" in text.upper()


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_empty_image_reports_low_confidence(client, register, auth, png_bytes):
    session = register("ocr@test.io")
    response = client.post("/v1/ocr",
                           files={"file": ("blank.png", png_bytes((400, 200)), "image/png")},
                           headers=auth(session))
    assert response.status_code == 200
    assert response.json()["text"] == ""
    assert response.json()["lowConfidence"] is True


@pytest.mark.skipif(not ocr.available(), reason="Tesseract not installed")
def test_ocr_noise_image_does_not_trigger_rotation_passes(monkeypatch):
    # A pure-noise image reads nothing, so the expensive rotation retries must
    # be skipped — only the preprocessing variants run (bounded work).
    import io
    import os

    from PIL import Image

    calls = {"n": 0}
    real_read = ocr._read

    def counting_read(image):
        calls["n"] += 1
        return real_read(image)

    monkeypatch.setattr(ocr, "_read", counting_read)

    noise = Image.frombytes("L", (256, 256), os.urandom(256 * 256))
    buffer = io.BytesIO()
    noise.save(buffer, format="PNG")
    text, _ = ocr.extract_text(buffer.getvalue())

    assert text == ""
    assert calls["n"] <= 4  # variants only, no rotation retries

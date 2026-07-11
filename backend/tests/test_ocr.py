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

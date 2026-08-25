"""Schmale Smoke-Tests: Upload → Liste → Auslieferung → Löschen, plus
Ablehnung ungültiger Dateitypen und Path-Traversal-Versuche.
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as pixelframe  # noqa: E402


def _client(tmp_path: Path) -> TestClient:
    pixelframe.DATA_DIR = tmp_path
    return TestClient(pixelframe.app)


def _fake_image_bytes(fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), color="red").save(buf, format=fmt)
    return buf.getvalue()


def test_upload_list_get_delete(tmp_path):
    client = _client(tmp_path)

    resp = client.post("/api/images", files={"file": ("foto.jpg", _fake_image_bytes(), "image/jpeg")})
    assert resp.status_code == 200
    filename = resp.json()["filename"]
    assert filename.endswith(".jpg")
    assert (tmp_path / filename).is_file()

    resp = client.get("/api/images")
    assert filename in resp.json()["images"]

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")

    resp = client.delete(f"/api/images/{filename}")
    assert resp.status_code == 200
    assert not (tmp_path / filename).is_file()

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 404


def test_upload_downscales_large_png(tmp_path):
    client = _client(tmp_path)
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), color="blue").save(buf, format="PNG")

    resp = client.post("/api/images", files={"file": ("gross.png", buf.getvalue(), "image/png")})
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    with Image.open(tmp_path / filename) as img:
        assert max(img.size) <= pixelframe.MAX_EDGE
        assert img.format == "JPEG"


def test_rejects_bad_extension(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/images", files={"file": ("test.txt", b"hallo", "text/plain")})
    assert resp.status_code == 400


def test_rejects_broken_image(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/images", files={"file": ("kaputt.jpg", b"das-ist-kein-bild", "image/jpeg")})
    assert resp.status_code == 400


def test_image_path_rejects_traversal(tmp_path):
    pixelframe.DATA_DIR = tmp_path
    with pytest.raises(Exception):
        pixelframe._image_path("../etc/passwd")

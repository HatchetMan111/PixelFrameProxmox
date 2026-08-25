"""Schmale Smoke-Tests: Upload → Liste → Auslieferung → Löschen, Reihenfolge,
Einstellungen, plus Ablehnung ungültiger Dateitypen und Path-Traversal.
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
    """Isoliertes Environment pro Test: tmp_path/images als DATA_DIR,
    tmp_path als STATE_DIR (order.json/settings.json) – wie im echten
    Layout data/ mit images/-Unterordner, aber pro Test frisch."""
    data_dir = tmp_path / "images"
    data_dir.mkdir()
    pixelframe.DATA_DIR = data_dir
    pixelframe.STATE_DIR = tmp_path
    pixelframe.ORDER_FILE = tmp_path / "order.json"
    pixelframe.SETTINGS_FILE = tmp_path / "settings.json"
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
    assert (pixelframe.DATA_DIR / filename).is_file()

    resp = client.get("/api/images")
    assert filename in resp.json()["images"]

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")

    resp = client.delete(f"/api/images/{filename}")
    assert resp.status_code == 200
    assert not (pixelframe.DATA_DIR / filename).is_file()

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 404


def test_upload_downscales_large_png(tmp_path):
    client = _client(tmp_path)
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), color="blue").save(buf, format="PNG")

    resp = client.post("/api/images", files={"file": ("gross.png", buf.getvalue(), "image/png")})
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    with Image.open(pixelframe.DATA_DIR / filename) as img:
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
    _client(tmp_path)
    with pytest.raises(Exception):
        pixelframe._image_path("../etc/passwd")


def test_settings_default_and_update(tmp_path):
    client = _client(tmp_path)

    resp = client.get("/api/settings")
    assert resp.json() == {"interval": 8, "shuffle": False}

    resp = client.put("/api/settings", json={"interval": 12, "shuffle": True})
    assert resp.status_code == 200
    assert resp.json() == {"interval": 12, "shuffle": True}

    resp = client.get("/api/settings")
    assert resp.json() == {"interval": 12, "shuffle": True}


def test_settings_rejects_too_short_interval(tmp_path):
    client = _client(tmp_path)
    resp = client.put("/api/settings", json={"interval": 1, "shuffle": False})
    assert resp.status_code == 400


def test_order_reorder_and_self_heal(tmp_path):
    client = _client(tmp_path)

    names = []
    for _ in range(3):
        resp = client.post("/api/images", files={"file": ("foto.jpg", _fake_image_bytes(), "image/jpeg")})
        names.append(resp.json()["filename"])

    resp = client.get("/api/images")
    assert resp.json()["images"] == names  # Upload-Reihenfolge

    reversed_names = list(reversed(names))
    resp = client.post("/api/order", json={"images": reversed_names})
    assert resp.status_code == 200
    assert resp.json()["images"] == reversed_names

    resp = client.get("/api/images")
    assert resp.json()["images"] == reversed_names

    # order.json enthält jetzt einen gelöschten Namen -> self-heal beim nächsten GET
    client.delete(f"/api/images/{reversed_names[0]}")
    resp = client.get("/api/images")
    assert reversed_names[0] not in resp.json()["images"]
    assert len(resp.json()["images"]) == 2

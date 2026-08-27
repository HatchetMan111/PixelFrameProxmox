"""Smoke-Tests: Upload (Bild+Video) → Liste → Auslieferung → Löschen,
Reihenfolge, Ausblenden, Einstellungen, Admin-Passwort, Ablehnung ungültiger
Dateitypen/zu großer Dateien und Path-Traversal.
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as pixelframe  # noqa: E402

AUTH = ("admin", "admin")  # Default-Admin-Passwort


def _client(tmp_path: Path) -> TestClient:
    """Isoliertes Environment pro Test: tmp_path/images als DATA_DIR,
    tmp_path als STATE_DIR (order.json/settings.json/admin.json)."""
    data_dir = tmp_path / "images"
    data_dir.mkdir()
    pixelframe.DATA_DIR = data_dir
    pixelframe.STATE_DIR = tmp_path
    pixelframe.ORDER_FILE = tmp_path / "order.json"
    pixelframe.SETTINGS_FILE = tmp_path / "settings.json"
    pixelframe.ADMIN_FILE = tmp_path / "admin.json"
    return TestClient(pixelframe.app)


def _fake_image_bytes(fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), color="red").save(buf, format=fmt)
    return buf.getvalue()


def _upload_image(client: TestClient, name: str = "foto.jpg") -> str:
    resp = client.post("/api/images", files={"file": (name, _fake_image_bytes(), "image/jpeg")}, auth=AUTH)
    assert resp.status_code == 200
    return resp.json()["filename"]


def test_upload_list_get_delete(tmp_path):
    client = _client(tmp_path)
    filename = _upload_image(client)
    assert (pixelframe.DATA_DIR / filename).is_file()

    resp = client.get("/api/images")  # öffentlich, kein Auth nötig
    assert filename in resp.json()["images"]

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")

    resp = client.delete(f"/api/images/{filename}", auth=AUTH)
    assert resp.status_code == 200
    assert not (pixelframe.DATA_DIR / filename).is_file()

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 404


def test_upload_downscales_large_png(tmp_path):
    client = _client(tmp_path)
    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), color="blue").save(buf, format="PNG")

    resp = client.post("/api/images", files={"file": ("gross.png", buf.getvalue(), "image/png")}, auth=AUTH)
    assert resp.status_code == 200
    filename = resp.json()["filename"]

    with Image.open(pixelframe.DATA_DIR / filename) as img:
        assert max(img.size) <= pixelframe.MAX_EDGE
        assert img.format == "JPEG"


def test_rejects_bad_extension(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/images", files={"file": ("test.txt", b"hallo", "text/plain")}, auth=AUTH)
    assert resp.status_code == 400


def test_rejects_broken_image(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/images", files={"file": ("kaputt.jpg", b"das-ist-kein-bild", "image/jpeg")}, auth=AUTH)
    assert resp.status_code == 400


def test_rejects_oversized_upload(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(pixelframe, "MAX_IMAGE_BYTES", 10)  # winziges Limit zum Testen
    resp = client.post("/api/images", files={"file": ("foto.jpg", _fake_image_bytes(), "image/jpeg")}, auth=AUTH)
    assert resp.status_code == 400
    assert not any(pixelframe.DATA_DIR.iterdir())  # keine Datei-Leiche zurückgelassen


def test_media_path_rejects_traversal(tmp_path):
    _client(tmp_path)
    with pytest.raises(Exception):
        pixelframe._media_path("../etc/passwd")


def test_settings_default_and_update(tmp_path):
    client = _client(tmp_path)

    resp = client.get("/api/settings")  # öffentlich
    assert resp.json() == {"interval": 8, "shuffle": False}

    resp = client.put("/api/settings", json={"interval": 12, "shuffle": True}, auth=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"interval": 12, "shuffle": True}

    resp = client.get("/api/settings")
    assert resp.json() == {"interval": 12, "shuffle": True}


def test_settings_rejects_too_short_interval(tmp_path):
    client = _client(tmp_path)
    resp = client.put("/api/settings", json={"interval": 1, "shuffle": False}, auth=AUTH)
    assert resp.status_code == 400


def test_settings_write_requires_auth(tmp_path):
    client = _client(tmp_path)
    resp = client.put("/api/settings", json={"interval": 12, "shuffle": True})  # kein Auth
    assert resp.status_code == 401


def test_media_reorder_and_self_heal(tmp_path):
    client = _client(tmp_path)
    names = [_upload_image(client) for _ in range(3)]

    resp = client.get("/api/images")
    assert resp.json()["images"] == names  # Upload-Reihenfolge

    reversed_names = list(reversed(names))
    resp = client.post(
        "/api/media",
        json={"media": [{"name": n, "hidden": False} for n in reversed_names]},
        auth=AUTH,
    )
    assert resp.status_code == 200

    resp = client.get("/api/images")
    assert resp.json()["images"] == reversed_names

    # order.json enthält jetzt einen gelöschten Namen -> self-heal beim nächsten GET
    client.delete(f"/api/images/{reversed_names[0]}", auth=AUTH)
    resp = client.get("/api/images")
    assert reversed_names[0] not in resp.json()["images"]
    assert len(resp.json()["images"]) == 2


def test_hide_and_show_media(tmp_path):
    client = _client(tmp_path)
    a = _upload_image(client, "a.jpg")
    b = _upload_image(client, "b.jpg")

    resp = client.post(
        "/api/media",
        json={"media": [{"name": a, "hidden": True}, {"name": b, "hidden": False}]},
        auth=AUTH,
    )
    assert resp.status_code == 200

    resp = client.get("/api/images")  # öffentlich, nur sichtbare
    assert resp.json()["images"] == [b]

    resp = client.get("/api/media", auth=AUTH)  # Admin sieht alles inkl. hidden-Flag
    media = {m["name"]: m["hidden"] for m in resp.json()["media"]}
    assert media == {a: True, b: False}

    # wieder einblenden
    client.post("/api/media", json={"media": [{"name": a, "hidden": False}, {"name": b, "hidden": False}]}, auth=AUTH)
    resp = client.get("/api/images")
    assert set(resp.json()["images"]) == {a, b}


def test_video_upload_stored_and_served(tmp_path):
    client = _client(tmp_path)
    # Kein echtes Video nötig: Videos werden nur gespeichert/ausgeliefert, nicht dekodiert.
    resp = client.post("/api/images", files={"file": ("clip.mp4", b"fake-mp4-bytes", "video/mp4")}, auth=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "video"
    filename = data["filename"]
    assert filename.endswith(".mp4")  # Originalformat bleibt erhalten, kein Transcoding

    resp = client.get("/api/images")
    assert filename in resp.json()["images"]

    resp = client.get(f"/images/{filename}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == b"fake-mp4-bytes"


def test_video_range_request_supported(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/images", files={"file": ("clip.mp4", b"0123456789", "video/mp4")}, auth=AUTH)
    filename = resp.json()["filename"]

    resp = client.get(f"/images/{filename}", headers={"Range": "bytes=2-5"})
    assert resp.status_code == 206
    assert resp.content == b"2345"


def test_admin_page_requires_password(tmp_path):
    client = _client(tmp_path)
    assert client.get("/upload").status_code == 401
    assert client.get("/upload", auth=("admin", "falsch")).status_code == 401
    assert client.get("/upload", auth=AUTH).status_code == 200


def test_change_password_flow(tmp_path):
    client = _client(tmp_path)
    resp = client.put("/api/admin/password", json={"new_password": "neuesPasswort123"}, auth=AUTH)
    assert resp.status_code == 200

    # altes Passwort funktioniert nicht mehr
    assert client.get("/upload", auth=AUTH).status_code == 401
    # neues Passwort funktioniert
    assert client.get("/upload", auth=("admin", "neuesPasswort123")).status_code == 200


def test_change_password_rejects_too_short(tmp_path):
    client = _client(tmp_path)
    resp = client.put("/api/admin/password", json={"new_password": "ab"}, auth=AUTH)
    assert resp.status_code == 400

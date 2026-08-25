"""PixelFrame – schlanker digitaler Bilderrahmen.

Kein DB-Server: das Dateisystem ist die Datenbank. Jede hochgeladene Datei
wird einmalig auf max. 1920px verkleinert, EXIF-korrigiert und als JPEG
gespeichert – der Bilderrahmen (altes Tablet) muss zur Laufzeit nur noch
anzeigen, nicht mehr rechnen. Reihenfolge und Anzeige-Einstellungen liegen
als kleine JSON-Dateien neben dem Bilder-Ordner.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PIXELFRAME_DATA_DIR", BASE_DIR.parent / "data" / "images"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = DATA_DIR.parent
ORDER_FILE = STATE_DIR / "order.json"
SETTINGS_FILE = STATE_DIR / "settings.json"

MAX_EDGE = 1920
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_SETTINGS = {"interval": 8, "shuffle": False}

app = FastAPI(title="PixelFrame")


class OrderPayload(BaseModel):
    images: list[str]


class SettingsPayload(BaseModel):
    interval: float
    shuffle: bool


def _safe_stem(name: str) -> str:
    stem = Path(name or "bild").stem
    cleaned = "".join(c for c in stem if c.isalnum() or c in "._-")
    return cleaned or "bild"


def _image_path(filename: str) -> Path:
    """Löst filename sicher innerhalb von DATA_DIR auf (kein Path-Traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Ungültiger Dateiname")
    path = DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "Bild nicht gefunden")
    return path


def _read_static(name: str) -> str:
    return (BASE_DIR / "static" / name).read_text(encoding="utf-8")


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ordered_filenames() -> list[str]:
    """Bilddateien in gespeicherter Reihenfolge. Heilt order.json automatisch:
    neu hochgeladene Dateien werden ans Ende angehängt, gelöschte entfernt."""
    existing = {p.name for p in DATA_DIR.iterdir() if p.is_file()}
    stored = _load_json(ORDER_FILE, [])
    order = [n for n in stored if n in existing]
    missing = sorted(existing - set(order))
    order.extend(missing)
    if order != stored:
        _save_json(ORDER_FILE, order)
    return order


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return _read_static("upload.html")


@app.get("/upload", response_class=HTMLResponse)
def upload_page() -> str:
    return _read_static("upload.html")


@app.get("/frame", response_class=HTMLResponse)
def frame_page() -> str:
    return _read_static("frame.html")


@app.get("/api/images")
def list_images() -> dict:
    return {"images": _ordered_filenames()}


@app.post("/api/order")
def set_order(payload: OrderPayload) -> dict:
    existing = {p.name for p in DATA_DIR.iterdir() if p.is_file()}
    order = [n for n in payload.images if n in existing]
    missing = sorted(existing - set(order))
    order.extend(missing)
    _save_json(ORDER_FILE, order)
    return {"images": order}


@app.get("/api/settings")
def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **_load_json(SETTINGS_FILE, {})}


@app.put("/api/settings")
def update_settings(payload: SettingsPayload) -> dict:
    if payload.interval < 2:
        raise HTTPException(400, "Anzeigedauer muss mindestens 2 Sekunden betragen")
    settings = {"interval": payload.interval, "shuffle": payload.shuffle}
    _save_json(SETTINGS_FILE, settings)
    return settings


@app.get("/images/{filename}")
def get_image(filename: str) -> FileResponse:
    return FileResponse(_image_path(filename))


@app.post("/api/images")
async def upload_image(file: UploadFile = File(...)) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Dateityp '{ext}' nicht erlaubt (erlaubt: {', '.join(sorted(ALLOWED_EXT))})")

    dest_name = f"{int(time.time() * 1000)}_{_safe_stem(file.filename)}.jpg"
    dest = DATA_DIR / dest_name
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    try:
        with tmp.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        with Image.open(tmp) as img:
            img = ImageOps.exif_transpose(img) or img
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((MAX_EDGE, MAX_EDGE))
            img.save(dest, "JPEG", quality=85, optimize=True)
    except Exception as exc:  # ungültige/kaputte Bilddatei
        raise HTTPException(400, f"Bild konnte nicht verarbeitet werden: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)

    order = _load_json(ORDER_FILE, [])
    order.append(dest_name)
    _save_json(ORDER_FILE, order)

    return {"filename": dest_name}


@app.delete("/api/images/{filename}")
def delete_image(filename: str) -> dict:
    path = _image_path(filename)
    path.unlink()
    order = [n for n in _load_json(ORDER_FILE, []) if n != filename]
    _save_json(ORDER_FILE, order)
    return {"deleted": filename}

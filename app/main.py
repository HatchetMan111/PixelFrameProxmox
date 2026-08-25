"""PixelFrame – schlanker digitaler Bilderrahmen.

Kein DB-Server: das Dateisystem ist die Datenbank. Jede hochgeladene Datei
wird einmalig auf max. 1920px verkleinert, EXIF-korrigiert und als JPEG
gespeichert – der Bilderrahmen (altes Tablet) muss zur Laufzeit nur noch
anzeigen, nicht mehr rechnen.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PIXELFRAME_DATA_DIR", BASE_DIR.parent / "data" / "images"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_EDGE = 1920
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

app = FastAPI(title="PixelFrame")


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
    files = sorted(p.name for p in DATA_DIR.iterdir() if p.is_file())
    return {"images": files}


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

    return {"filename": dest_name}


@app.delete("/api/images/{filename}")
def delete_image(filename: str) -> dict:
    path = _image_path(filename)
    path.unlink()
    return {"deleted": filename}

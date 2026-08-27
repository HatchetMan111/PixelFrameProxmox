"""PixelFrame – schlanker digitaler Bilderrahmen (Bilder + Videos).

Kein DB-Server: das Dateisystem ist die Datenbank. Bilder werden einmalig auf
max. 1920px verkleinert, EXIF-korrigiert und als JPEG gespeichert. Videos
werden unverändert gespeichert (kein Transcoding, kein ffmpeg nötig) und in
der Diashow bis zum Ende abgespielt. Reihenfolge + Sichtbarkeit (ausgeblendet
oder nicht) liegen zusammen in einer kleinen order.json, Anzeige-Einstellungen
in settings.json – beide neben dem Medien-Ordner.

Öffentlich (kein Login, für die Tablet-Anzeige): /frame, GET /api/images,
GET /images/{name}, GET /api/settings.
Nur mit Admin-Passwort (HTTP Basic, Default "admin"): /upload, Upload/Löschen,
Reihenfolge/Sichtbarkeit ändern, Einstellungen ändern, Passwort ändern.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from PIL import Image, ImageOps
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("PIXELFRAME_DATA_DIR", BASE_DIR.parent / "data" / "images"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = DATA_DIR.parent
ORDER_FILE = STATE_DIR / "order.json"
SETTINGS_FILE = STATE_DIR / "settings.json"
ADMIN_FILE = STATE_DIR / "admin.json"

MAX_EDGE = 1920
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".webm"}
ALLOWED_EXT = IMAGE_EXT | VIDEO_EXT
MAX_IMAGE_BYTES = 50 * 1024 * 1024   # 50 MB – reicht für jedes Handyfoto
MAX_VIDEO_BYTES = 300 * 1024 * 1024  # 300 MB – reicht für kurze Videoclips
MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".mp4": "video/mp4", ".webm": "video/webm",
}
DEFAULT_SETTINGS = {"interval": 8, "shuffle": False}
DEFAULT_ADMIN_PASSWORD = "admin"

app = FastAPI(title="PixelFrame")
security = HTTPBasic()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _get_password_hash() -> str:
    data = _load_json(ADMIN_FILE, None)
    if isinstance(data, dict) and "password_hash" in data:
        return data["password_hash"]
    default_hash = _hash_password(DEFAULT_ADMIN_PASSWORD)
    _save_json(ADMIN_FILE, {"password_hash": default_hash})
    return default_hash


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    expected = _get_password_hash()
    given = _hash_password(credentials.password)
    if not secrets.compare_digest(given, expected):
        raise HTTPException(401, "Falsches Passwort", headers={"WWW-Authenticate": 'Basic realm="PixelFrame Admin"'})


admin_router = APIRouter(dependencies=[Depends(require_admin)])


class MediaEntryPayload(BaseModel):
    name: str
    hidden: bool = False


class MediaListPayload(BaseModel):
    media: list[MediaEntryPayload]


class SettingsPayload(BaseModel):
    interval: float
    shuffle: bool


class PasswordChangePayload(BaseModel):
    new_password: str


def _safe_stem(name: str) -> str:
    stem = Path(name or "datei").stem
    cleaned = "".join(c for c in stem if c.isalnum() or c in "._-")
    return cleaned or "datei"


def _media_path(filename: str) -> Path:
    """Löst filename sicher innerhalb von DATA_DIR auf (kein Path-Traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Ungültiger Dateiname")
    path = DATA_DIR / filename
    if not path.is_file():
        raise HTTPException(404, "Datei nicht gefunden")
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


def _normalize_entry(entry) -> dict | None:
    """Alte order.json-Formate (reine Dateinamen-Strings, vor Einführung des
    Ausblenden-Features) automatisch in {"name":..., "hidden":...} migrieren."""
    if isinstance(entry, str):
        return {"name": entry, "hidden": False}
    if isinstance(entry, dict) and isinstance(entry.get("name"), str):
        return {"name": entry["name"], "hidden": bool(entry.get("hidden", False))}
    return None


def _ordered_entries() -> list[dict]:
    """Alle Mediendateien mit Reihenfolge & Sichtbarkeit. Heilt order.json
    automatisch: neue Dateien werden angehängt (sichtbar), gelöschte entfernt,
    altes Format migriert."""
    existing = {p.name for p in DATA_DIR.iterdir() if p.is_file()}
    stored_raw = _load_json(ORDER_FILE, [])
    normalized, seen = [], set()
    for raw in stored_raw:
        entry = _normalize_entry(raw)
        if entry and entry["name"] in existing and entry["name"] not in seen:
            normalized.append(entry)
            seen.add(entry["name"])
    missing = sorted(existing - seen)
    normalized.extend({"name": n, "hidden": False} for n in missing)
    if normalized != stored_raw:
        _save_json(ORDER_FILE, normalized)
    return normalized


def _save_upload_bounded(file: UploadFile, dest: Path, max_bytes: int) -> None:
    """Kopiert file in Chunks nach dest; bricht ab und räumt auf, falls das
    konfigurierte Limit überschritten wird (Schutz vor vollem LXC-Storage)."""
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(400, f"Datei zu groß (Limit: {max_bytes // (1024 * 1024)} MB)")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise


# ---------- Öffentliche Routen (Tablet-Anzeige, kein Login) ----------

@app.get("/frame", response_class=HTMLResponse)
def frame_page() -> str:
    return _read_static("frame.html")


@app.get("/api/images")
def list_images() -> dict:
    return {"images": [e["name"] for e in _ordered_entries() if not e["hidden"]]}


@app.get("/api/settings")
def get_settings() -> dict:
    return {**DEFAULT_SETTINGS, **_load_json(SETTINGS_FILE, {})}


@app.get("/images/{filename}")
def get_media(filename: str) -> FileResponse:
    path = _media_path(filename)
    return FileResponse(path, media_type=MEDIA_TYPES.get(path.suffix.lower()))


# ---------- Admin-Routen (HTTP Basic Auth erforderlich) ----------

@admin_router.get("/", response_class=HTMLResponse)
def root() -> str:
    return _read_static("upload.html")


@admin_router.get("/upload", response_class=HTMLResponse)
def upload_page() -> str:
    return _read_static("upload.html")


@admin_router.get("/api/media")
def list_media() -> dict:
    return {"media": _ordered_entries()}


@admin_router.post("/api/media")
def set_media(payload: MediaListPayload) -> dict:
    existing = {p.name for p in DATA_DIR.iterdir() if p.is_file()}
    entries, seen = [], set()
    for item in payload.media:
        if item.name in existing and item.name not in seen:
            entries.append({"name": item.name, "hidden": item.hidden})
            seen.add(item.name)
    missing = sorted(existing - seen)
    entries.extend({"name": n, "hidden": False} for n in missing)
    _save_json(ORDER_FILE, entries)
    return {"media": entries}


@admin_router.put("/api/settings")
def update_settings(payload: SettingsPayload) -> dict:
    if payload.interval < 2:
        raise HTTPException(400, "Anzeigedauer muss mindestens 2 Sekunden betragen")
    settings = {"interval": payload.interval, "shuffle": payload.shuffle}
    _save_json(SETTINGS_FILE, settings)
    return settings


@admin_router.put("/api/admin/password")
def change_password(payload: PasswordChangePayload) -> dict:
    if len(payload.new_password) < 4:
        raise HTTPException(400, "Neues Passwort muss mindestens 4 Zeichen haben")
    _save_json(ADMIN_FILE, {"password_hash": _hash_password(payload.new_password)})
    return {"ok": True}


@admin_router.post("/api/images")
async def upload_media(file: UploadFile = File(...)) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Dateityp '{ext}' nicht erlaubt (erlaubt: {', '.join(sorted(ALLOWED_EXT))})")

    is_video = ext in VIDEO_EXT
    max_bytes = MAX_VIDEO_BYTES if is_video else MAX_IMAGE_BYTES

    if is_video:
        dest_name = f"{int(time.time() * 1000)}_{_safe_stem(file.filename)}{ext}"
        dest = DATA_DIR / dest_name
        _save_upload_bounded(file, dest, max_bytes)
    else:
        dest_name = f"{int(time.time() * 1000)}_{_safe_stem(file.filename)}.jpg"
        dest = DATA_DIR / dest_name
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            _save_upload_bounded(file, tmp, max_bytes)
            with Image.open(tmp) as img:
                img = ImageOps.exif_transpose(img) or img
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                img.thumbnail((MAX_EDGE, MAX_EDGE))
                img.save(dest, "JPEG", quality=85, optimize=True)
        except HTTPException:
            raise
        except Exception as exc:  # ungültige/kaputte Bilddatei
            raise HTTPException(400, f"Bild konnte nicht verarbeitet werden: {exc}") from exc
        finally:
            tmp.unlink(missing_ok=True)

    entries = _load_json(ORDER_FILE, [])
    entries.append({"name": dest_name, "hidden": False})
    _save_json(ORDER_FILE, entries)

    return {"filename": dest_name, "type": "video" if is_video else "image"}


@admin_router.delete("/api/images/{filename}")
def delete_media(filename: str) -> dict:
    path = _media_path(filename)
    path.unlink()
    entries = [e for e in _load_json(ORDER_FILE, []) if _normalize_entry(e) and _normalize_entry(e)["name"] != filename]
    _save_json(ORDER_FILE, entries)
    return {"deleted": filename}


app.include_router(admin_router)

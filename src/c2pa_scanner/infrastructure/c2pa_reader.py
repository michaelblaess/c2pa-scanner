"""C2PA-Leser: Adapter um die c2pa-Lib. Liest aus Datei ODER aus Bytes (Web)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

# Magic-Bytes -> MIME (nur Formate, die c2pa lesen kann).
_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]


def _sniff_mime(data: bytes, fallback: str) -> str:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heix", b"hevc", b"mif1"):
            return "image/heic"
    return fallback


def _find_digital_source_type(obj: Any) -> str | None:
    """Sucht rekursiv den ersten 'digitalSourceType'-Wert im Manifest-JSON."""
    if isinstance(obj, dict):
        value = obj.get("digitalSourceType")
        if isinstance(value, str) and value:
            return value
        for child in obj.values():
            found = _find_digital_source_type(child)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_digital_source_type(item)
            if found is not None:
                return found
    return None


def _read_manifest(reader: Any) -> tuple[bool, str | None]:
    if reader is None:
        return (False, None)
    try:
        parsed = json.loads(reader.json())
    finally:
        reader.close()
    return (True, _find_digital_source_type(parsed))


def image_size(data: bytes) -> tuple[int, int]:
    """Ermittelt (Breite, Hoehe) eines Bildes aus Bytes; (0, 0) wenn nicht lesbar."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            return (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001 - nicht lesbares Bild -> unbekannte Groesse
        return (0, 0)


def read_bytes(data: bytes, content_type: str) -> tuple[bool, str | None]:
    """Liest C2PA aus rohen Bild-Bytes. content_type = HTTP-Content-Type oder ''."""
    from c2pa import Reader

    mime = content_type.split(";")[0].strip().lower()
    if not mime.startswith("image/"):
        mime = _sniff_mime(data, mime)
    if not mime.startswith("image/"):
        return (False, None)
    try:
        reader = Reader.try_create(mime, io.BytesIO(data))
    except Exception:  # noqa: BLE001 - nicht unterstuetztes/defektes Format -> kein Manifest
        return (False, None)
    return _read_manifest(reader)


class C2paLibReader:
    """Liest C2PA-Manifeste aus lokalen Dateien (Tests, Master-Dateien)."""

    def read(self, path: Path) -> tuple[bool, str | None]:
        from c2pa import Reader

        reader = Reader.try_create(str(path))
        return _read_manifest(reader)

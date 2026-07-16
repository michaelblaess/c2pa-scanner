"""Herkunft-/C2PA-Leser: liest aus lokalen Dateien ODER aus Bytes (Web).

Primaersignal ist das C2PA-Manifest (digitalSourceType). Zusaetzlich werden
XMP und EXIF ausgewertet: Adobe Firefly/Photoshop schreiben den
`Iptc4xmpExt:DigitalSourceType` oft auch ins XMP (ohne gueltiges C2PA), und
EXIF/XMP nennen das erzeugende Tool (Software/CreatorTool). So werden auch
Bilder erkannt, die ihre C2PA-Signatur beim Resize verloren, aber XMP behalten.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

_DST_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
_DST_RE = re.compile(r"digitalsourcetype/([A-Za-z]+)", re.IGNORECASE)
_CREATORTOOL_RE = re.compile(
    r"CreatorTool>\s*([^<]+?)\s*<|CreatorTool=[\"']([^\"']+)[\"']", re.IGNORECASE
)


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


def _resolve_mime(data: bytes, content_type: str) -> str:
    mime = content_type.split(";")[0].strip().lower()
    if not mime.startswith("image/"):
        mime = _sniff_mime(data, mime)
    return mime


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


def _find_generator(obj: Any) -> str | None:
    """Sucht das erzeugende/signierende Tool (claim_generator) im Manifest-JSON."""
    if isinstance(obj, dict):
        info = obj.get("claim_generator_info")
        if isinstance(info, list) and info and isinstance(info[0], dict):
            name = info[0].get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        generator = obj.get("claim_generator")
        if isinstance(generator, str) and generator.strip():
            return generator.split("/")[0].strip() or generator.strip()
        for child in obj.values():
            found = _find_generator(child)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_generator(item)
            if found is not None:
                return found
    return None


def _read_c2pa(data: bytes, mime: str) -> tuple[bool, str | None, str | None]:
    """Liest das C2PA-Manifest: (has_c2pa, digital_source_type, generator)."""
    from c2pa import Reader

    if not mime.startswith("image/"):
        return (False, None, None)
    try:
        reader = Reader.try_create(mime, io.BytesIO(data))
    except Exception:  # noqa: BLE001 - nicht unterstuetztes/defektes Format
        return (False, None, None)
    if reader is None:
        return (False, None, None)
    try:
        parsed = json.loads(reader.json())
    finally:
        reader.close()
    return (True, _find_digital_source_type(parsed), _find_generator(parsed))


def _read_xmp_exif(data: bytes) -> tuple[str | None, str | None]:
    """Liest digitalSourceType (XMP) und das Tool (XMP CreatorTool / EXIF Software)."""
    from PIL import Image

    dst: str | None = None
    generator: str | None = None
    try:
        with Image.open(io.BytesIO(data)) as img:
            xmp = img.info.get("xmp")
            if isinstance(xmp, bytes):
                xmp = xmp.decode("utf-8", "ignore")
            if isinstance(xmp, str) and xmp:
                match = _DST_RE.search(xmp)
                if match:
                    dst = _DST_BASE + match.group(1)
                tool = _CREATORTOOL_RE.search(xmp)
                if tool:
                    generator = (tool.group(1) or tool.group(2) or "").strip() or None
            if generator is None:
                exif = img.getexif()
                software = exif.get(305) if exif else None  # 305 = Software
                if isinstance(software, str) and software.strip():
                    generator = software.strip()
    except Exception:  # noqa: BLE001 - kein/kaputtes XMP-EXIF ist kein Fehler
        return (dst, generator)
    return (dst, generator)


def image_size(data: bytes) -> tuple[int, int]:
    """Ermittelt (Breite, Hoehe) eines Bildes aus Bytes; (0, 0) wenn nicht lesbar."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            return (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001 - nicht lesbares Bild -> unbekannte Groesse
        return (0, 0)


def read_bytes(data: bytes, content_type: str) -> tuple[bool, str | None]:
    """Liest nur das C2PA-Ergebnis (has_c2pa, digital_source_type) - fuer Tests/Einfachfaelle."""
    has_c2pa, dst, _ = _read_c2pa(data, _resolve_mime(data, content_type))
    return (has_c2pa, dst)


def read_provenance(data: bytes, content_type: str) -> tuple[bool, str | None, str | None]:
    """Kombiniert C2PA + XMP/EXIF: (has_c2pa, digital_source_type, generator)."""
    mime = _resolve_mime(data, content_type)
    has_c2pa, dst, generator = _read_c2pa(data, mime)
    xmp_dst, xmp_generator = _read_xmp_exif(data)
    if dst is None:
        dst = xmp_dst
    if generator is None:
        generator = xmp_generator
    return (has_c2pa, dst, generator)


def read_manifest_json(data: bytes, content_type: str) -> str | None:
    """Gibt das rohe C2PA-Manifest als eingerueckten JSON-String zurueck (oder None)."""
    from c2pa import Reader

    mime = _resolve_mime(data, content_type)
    if not mime.startswith("image/"):
        return None
    try:
        reader = Reader.try_create(mime, io.BytesIO(data))
    except Exception:  # noqa: BLE001 - kein/kaputtes Manifest
        return None
    if reader is None:
        return None
    try:
        raw = str(reader.json())
    finally:
        reader.close()
    try:
        return json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return raw


class C2paLibReader:
    """Liest C2PA-Manifeste aus lokalen Dateien (Tests, Master-Dateien)."""

    def read(self, path: Path) -> tuple[bool, str | None]:
        from c2pa import Reader

        reader = Reader.try_create(str(path))
        if reader is None:
            return (False, None)
        try:
            parsed = json.loads(reader.json())
        finally:
            reader.close()
        return (True, _find_digital_source_type(parsed))

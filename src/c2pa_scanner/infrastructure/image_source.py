"""Bildquelle: zaehlt Bilddateien in einem Verzeichnis auf."""

from __future__ import annotations

from pathlib import Path

IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".gif", ".heic", ".heif", ".avif"}
)


def iter_images(root: Path, recursive: bool = True) -> list[Path]:
    """Sammelt alle unterstuetzten Bilddateien unter root (sortiert)."""
    if root.is_file():
        return [root] if root.suffix.lower() in IMAGE_SUFFIXES else []
    pattern = "**/*" if recursive else "*"
    files = [
        p for p in root.glob(pattern) if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    return sorted(files)

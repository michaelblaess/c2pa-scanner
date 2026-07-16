"""Protocols (Interfaces) - werden in infrastructure/ implementiert."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class C2paReadResult(Protocol):
    """Struktur des Lese-Ergebnisses (has_c2pa, digital_source_type)."""

    has_c2pa: bool
    digital_source_type: str | None


class C2paReader(Protocol):
    """Liest den C2PA-Herkunftsnachweis aus einer Bilddatei."""

    def read(self, path: Path) -> tuple[bool, str | None]:
        """Gibt (has_c2pa, digital_source_type) zurueck; digital_source_type None wenn keiner."""
        ...

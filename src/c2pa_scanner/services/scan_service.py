"""ScanService: orchestriert Bilder -> C2PA lesen -> klassifizieren."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.domain.protocols import C2paReader
from c2pa_scanner.services.classify import classify


class ScanService:
    """Prueft eine Menge von Bildern auf C2PA-Herkunft."""

    def __init__(self, reader: C2paReader) -> None:
        self._reader = reader

    def scan_paths(self, paths: Iterable[Path]) -> list[ImageFinding]:
        """Prueft alle uebergebenen Pfade und liefert je ein ImageFinding."""
        findings: list[ImageFinding] = []
        for path in paths:
            findings.append(self._scan_one(path))
        return findings

    def _scan_one(self, path: Path) -> ImageFinding:
        try:
            has_c2pa, dst = self._reader.read(path)
        except Exception as exc:  # noqa: BLE001 - defensive: ein defektes Bild darf den Lauf nicht killen
            return ImageFinding(str(path), False, None, Verdict.ERROR, str(exc))
        return ImageFinding(str(path), has_c2pa, dst, classify(dst, has_c2pa))

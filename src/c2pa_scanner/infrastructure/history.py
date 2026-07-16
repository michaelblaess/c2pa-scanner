"""History der gescannten Sitemaps unter ~/.c2pa-scanner/history.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    """Ein History-Eintrag: Sitemap plus Kennzahlen des letzten Laufs."""

    sitemap: str
    at: str
    pages: int
    images: int
    needs_label: int


class HistoryStore:
    """Laedt/speichert die Sitemap-History (neueste zuerst, dedupliziert)."""

    def __init__(self, limit: int = 50) -> None:
        self._dir = Path.home() / ".c2pa-scanner"
        self._file = self._dir / "history.json"
        self._limit = limit

    @property
    def path(self) -> Path:
        return self._file

    def load(self) -> list[HistoryEntry]:
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        entries: list[HistoryEntry] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            entries.append(
                HistoryEntry(
                    sitemap=str(item.get("sitemap", "")),
                    at=str(item.get("at", "")),
                    pages=int(item.get("pages", 0)),
                    images=int(item.get("images", 0)),
                    needs_label=int(item.get("needs_label", 0)),
                )
            )
        return entries

    def add(self, entry: HistoryEntry) -> None:
        existing = [e for e in self.load() if e.sitemap != entry.sitemap]
        entries = [entry, *existing][: self._limit]
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps([e.__dict__ for e in entries], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

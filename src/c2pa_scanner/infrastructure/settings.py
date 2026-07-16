"""Einfacher JSON-Settings-Store unter ~/.c2pa-scanner/settings.json."""

from __future__ import annotations

import json
from pathlib import Path


class JsonSettingsStore:
    """Laedt/speichert die App-Einstellungen als JSON im Home-Verzeichnis."""

    def __init__(self) -> None:
        self._dir = Path.home() / ".c2pa-scanner"
        self._file = self._dir / "settings.json"

    @property
    def path(self) -> Path:
        return self._file

    def load(self) -> dict[str, object]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, object]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

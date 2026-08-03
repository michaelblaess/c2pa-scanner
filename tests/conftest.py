"""Gemeinsame Test-Vorbereitung.

Ohne geladene Sprachdatei liefert ``t()`` den Schluessel statt des Textes -
Tests, die auf Beschriftungen pruefen, wuerden dann gegen "table.status" statt
"Status" laufen. Darum wird fuer alle Tests eine feste Sprache geladen.

Ausserdem wird das Home-Verzeichnis umgelegt: die Einstellungen liegen unter
``~/.c2pa-scanner``, und die App schreibt beim Start hinein (etwa das Thema).
Ohne diese Trennung wuerde ein Testlauf die echten Einstellungen veraendern.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from c2pa_scanner.i18n import load_locale


@pytest.fixture(autouse=True)
def _german_locale() -> None:
    """Laedt Deutsch fuer jeden Test - unabhaengig von der Umgebung der Maschine."""
    load_locale("de")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Legt Path.home() auf ein Wegwerf-Verzeichnis (Windows liest USERPROFILE)."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path

"""Gemeinsame Test-Vorbereitung.

Ohne geladene Sprachdatei liefert ``t()`` den Schluessel statt des Textes -
Tests, die auf Beschriftungen pruefen, wuerden dann gegen "table.status" statt
"Status" laufen. Darum wird fuer alle Tests eine feste Sprache geladen.
"""

from __future__ import annotations

import pytest

from c2pa_scanner.i18n import load_locale


@pytest.fixture(autouse=True)
def _german_locale() -> None:
    """Laedt Deutsch fuer jeden Test - unabhaengig von der Umgebung der Maschine."""
    load_locale("de")

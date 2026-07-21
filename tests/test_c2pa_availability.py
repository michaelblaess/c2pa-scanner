"""Tests fuer den Verfuegbarkeits-Guard der nativen C2PA-Bibliothek.

Fehlt c2pa_c (die native Lib des c2pa-python-Wheels), wirft schon `import c2pa`.
Ohne Guard liefe der Scan weiter und meldete JEDES Bild als "kein C2PA" - ein
still falsch-negatives Ergebnis. Der Guard muss diesen Fall hart abbrechen.
"""

from __future__ import annotations

import sys

import pytest

from c2pa_scanner.infrastructure import c2pa_reader
from c2pa_scanner.infrastructure.c2pa_reader import (
    C2paUnavailableError,
    ensure_c2pa_available,
)


class TestEnsureC2paAvailable:
    def test_passes_when_library_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Im Dev-Environment ist die native Lib da - der Guard laesst durch."""
        monkeypatch.setattr(c2pa_reader, "_availability", None)
        ensure_c2pa_available()

    def test_raises_when_import_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ein None-Eintrag in sys.modules laesst `import c2pa` real scheitern."""
        monkeypatch.setattr(c2pa_reader, "_availability", None)
        monkeypatch.setitem(sys.modules, "c2pa", None)
        with pytest.raises(C2paUnavailableError):
            ensure_c2pa_available()

    def test_failure_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Der Fehlergrund wird gecacht - kein erneuter Importversuch pro Bild."""
        monkeypatch.setattr(
            c2pa_reader, "_availability", "RuntimeError: Could not find c2pa_c.dll"
        )
        with pytest.raises(C2paUnavailableError, match="c2pa_c.dll"):
            ensure_c2pa_available()

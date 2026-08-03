"""Ein Absturz muss auf Platte landen, nicht nur im Dialog.

Der CrashGuard zeigt den Traceback im Fehlerdialog. Faellt dieser beim Neuaufbau
selbst mit, geht der Bericht verloren - und unter Windows bleibt nur
Maus-Steuerzeichen-Muell im Terminal zurueck. Darum wird der Bericht vorher
geschrieben.
"""

from __future__ import annotations

from pathlib import Path

from c2pa_scanner import __version__
from c2pa_scanner.app import C2paScannerApp
from c2pa_scanner.infrastructure.settings import CRASH_LOG_NAME, JsonSettingsStore


def _crash_file() -> Path:
    return JsonSettingsStore().path.parent / CRASH_LOG_NAME


class TestCrashLog:
    def test_traceback_is_written_to_disk(self) -> None:
        app = C2paScannerApp()
        try:
            raise RuntimeError("kaputt zum Testen")
        except RuntimeError as error:
            app._persist_crash(error)

        inhalt = _crash_file().read_text(encoding="utf-8")
        assert "kaputt zum Testen" in inhalt
        assert "RuntimeError" in inhalt
        assert __version__ in inhalt, "ohne Version laesst sich der Bericht nicht zuordnen"
        assert "Traceback" in inhalt

    def test_reports_are_appended(self) -> None:
        """Ein zweiter Absturz darf den ersten nicht ueberschreiben."""
        app = C2paScannerApp()
        for text in ("erster Fehler", "zweiter Fehler"):
            try:
                raise ValueError(text)
            except ValueError as error:
                app._persist_crash(error)

        inhalt = _crash_file().read_text(encoding="utf-8")
        assert "erster Fehler" in inhalt
        assert "zweiter Fehler" in inhalt

    def test_handle_exception_persists_before_the_dialog(self) -> None:
        """Der Haken sitzt vor dem CrashGuard - sonst haengt der Bericht am Dialog."""
        app = C2paScannerApp()
        weitergereicht: list[BaseException] = []

        # Statt des echten CrashGuard-Dialogs nur mitschreiben, dass er drankaeme.
        app._crash_guard_busy = True  # laesst den Mixin an App._handle_exception weiterreichen
        error = RuntimeError("Absturz im Betrieb")
        try:
            app._handle_exception(error)
        except Exception as exc:  # noqa: BLE001 - Textual beendet sich hier normalerweise
            weitergereicht.append(exc)

        inhalt = _crash_file().read_text(encoding="utf-8")
        assert "Absturz im Betrieb" in inhalt


class TestFaultLog:
    """faulthandler faengt ab, was unterhalb von Pythons Exception-Handling liegt."""

    def test_start_line_and_handler(self) -> None:
        import faulthandler

        from c2pa_scanner.__main__ import _enable_faulthandler

        _enable_faulthandler()
        datei = JsonSettingsStore().path.parent / "fault.log"
        assert datei.is_file(), "fault.log wurde nicht angelegt"
        erste_zeile = datei.read_text(encoding="utf-8").strip().split("\n")[0]
        # Die Startzeile ist der Beleg dafuer, dass der Prozess ueberhaupt lief -
        # fehlt danach alles Weitere, wurde er von aussen abgeraeumt.
        assert erste_zeile.startswith("===== Start ")
        assert __version__ in erste_zeile
        assert faulthandler.is_enabled()

    def test_end_line_closes_the_session(self) -> None:
        """Das Gegenstueck zur Startzeile - ohne sie ist die Datei nicht deutbar.

        Steht nur eine Startzeile da, wurde der Prozess hart abgeraeumt; mit
        Endzeile ist er sauber gelaufen. Genau diese Unterscheidung ist der Zweck.
        """
        from c2pa_scanner.__main__ import _enable_faulthandler, _write_fault_end

        _enable_faulthandler()
        _write_fault_end()  # ruft sonst atexit auf
        zeilen = (JsonSettingsStore().path.parent / "fault.log").read_text(
            encoding="utf-8"
        ).strip().split("\n")
        assert any(z.startswith("===== Start ") for z in zeilen)
        assert any(z.startswith("===== Ende ") for z in zeilen)

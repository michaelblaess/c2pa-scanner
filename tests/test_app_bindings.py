"""Fusszeile: 'Scan abbrechen' erscheint nur waehrend eines Laufs.

Vor dieser Aenderung liess sich ein Lauf nur mit 'q' stoppen - und damit war
auch die Tabelle weg. Die Taste muss deshalb waehrend des Laufs da sein, sonst
nicht, und sie muss beim Dienst ankommen.
"""

from __future__ import annotations

import asyncio

from c2pa_scanner.app import C2paScannerApp


class FakeScanService:
    """Steht fuer einen laufenden Scan, ohne Netz und ohne Browser."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _visible_actions(app: C2paScannerApp) -> set[str]:
    """Aktionen, deren Taste tatsaechlich Platz in der Fusszeile belegt."""
    return {
        str(getattr(key, "action", ""))
        for key in app.query("FooterKey")
        if key.display and key.region.width > 0
    }


class TestCancelBinding:
    def test_cancel_key_appears_only_while_scanning(self) -> None:
        async def scenario() -> tuple[set[str], set[str], bool, set[str]]:
            app = C2paScannerApp()
            app._ask_disclaimer = lambda: None  # der Hinweis blockiert sonst den Start
            async with app.run_test(size=(200, 45)) as pilot:
                for _ in range(4):
                    await pilot.pause()
                idle = _visible_actions(app)

                service = FakeScanService()
                app._scanning = True
                app._scan_service = service
                app.refresh_bindings()
                for _ in range(4):
                    await pilot.pause()
                running = _visible_actions(app)

                await pilot.press("x")
                await pilot.pause()
                cancelled = service.cancelled

                app._scanning = False
                app._scan_service = None
                app.refresh_bindings()
                for _ in range(4):
                    await pilot.pause()
                after = _visible_actions(app)
            return idle, running, cancelled, after

        idle, running, cancelled, after = asyncio.run(scenario())

        assert "cancel_scan" not in idle, "Abbrechen steht im Fuss, obwohl nichts laeuft"
        assert "scan" in idle

        assert "cancel_scan" in running, "Abbrechen fehlt im Fuss, obwohl ein Lauf laeuft"
        assert "scan" not in running, "Scannen wird waehrend eines Laufs weiter angeboten"

        assert cancelled is True, "'x' hat den Abbruch nicht an den Dienst gemeldet"

        assert "cancel_scan" not in after
        assert "scan" in after

    def test_cancel_without_scan_only_warns(self) -> None:
        """Ohne Lauf darf die Aktion nichts kaputtmachen (etwa ueber die Befehlsliste)."""

        async def scenario() -> None:
            app = C2paScannerApp()
            app._ask_disclaimer = lambda: None
            async with app.run_test(size=(200, 45)) as pilot:
                await pilot.pause()
                app.action_cancel_scan()  # kein Lauf aktiv
                await pilot.pause()

        asyncio.run(scenario())

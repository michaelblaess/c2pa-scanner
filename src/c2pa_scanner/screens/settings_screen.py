"""Settings-Dialog (erbt von BaseSettingsScreen)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Checkbox, Label, TabPane
from textual_widgets import BaseSettingsScreen

from c2pa_scanner.infrastructure.settings import JsonSettingsStore


class SettingsScreen(BaseSettingsScreen):  # type: ignore[misc]
    """Einstellungen: Scan-Optionen plus Speicherort-Tab."""

    def app_tabs(self) -> ComposeResult:
        with (
            TabPane("Scan", id="settings-tab-scan"),
            VerticalScroll(),
            Horizontal(classes="settings-row"),
        ):
            yield Label("Unterordner")
            yield Checkbox(
                "Unterordner rekursiv einbeziehen",
                value=bool(self._settings.get("recursive", True)),
                id="set-recursive",
            )

    def collect_app_settings(self, settings: dict[str, object]) -> None:
        settings["recursive"] = self.query_one("#set-recursive", Checkbox).value

    def storage_paths(self) -> list[tuple[str, Path]]:
        return [("Einstellungen", JsonSettingsStore().path)]

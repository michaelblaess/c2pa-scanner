"""Settings-Dialog (erbt von BaseSettingsScreen)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Checkbox, Input, Label, TabPane
from textual_widgets import BaseSettingsScreen

from c2pa_scanner.infrastructure.settings import JsonSettingsStore


class SettingsScreen(BaseSettingsScreen):  # type: ignore[misc]
    """Einstellungen: Netzwerk (Proxy), Anzeige, plus Speicherort-Tab."""

    def app_tabs(self) -> ComposeResult:
        with (
            TabPane("Scan", id="settings-tab-scan"),
            VerticalScroll(),
            Horizontal(classes="settings-row"),
        ):
            yield Label("Min. Bildgröße")
            yield Input(
                value=str(self._settings.get("min_image_size", 0)),
                placeholder="0 = aus; sonst px (längste Kante) - kleinere werden nicht gescannt",
                id="set-min-size",
                type="integer",
            )
        with (
            TabPane("Netzwerk", id="settings-tab-net"),
            VerticalScroll(),
            Horizontal(classes="settings-row"),
        ):
            yield Label("Proxy-URL")
            yield Input(
                value=str(self._settings.get("proxy_url", "")),
                placeholder="http://proxy-host:port (Zscaler/Corporate)",
                id="set-proxy",
            )
        with (
            TabPane("Anzeige", id="settings-tab-view"),
            VerticalScroll(),
            Horizontal(classes="settings-row"),
        ):
            yield Label("Bildvorschau")
            yield Checkbox(
                "Grafische Vorschau (Sixel/TGP) - Neustart nötig; sonst Text-Vorschau",
                value=bool(self._settings.get("graphics_preview", False)),
                id="set-graphics",
            )

    def collect_app_settings(self, settings: dict[str, object]) -> None:
        settings["proxy_url"] = self.query_one("#set-proxy", Input).value.strip()
        settings["graphics_preview"] = self.query_one("#set-graphics", Checkbox).value
        raw = self.query_one("#set-min-size", Input).value.strip()
        try:
            settings["min_image_size"] = max(0, int(raw)) if raw else 0
        except ValueError:
            settings["min_image_size"] = 0

    def storage_paths(self) -> list[tuple[str, Path]]:
        return [("Einstellungen", JsonSettingsStore().path)]

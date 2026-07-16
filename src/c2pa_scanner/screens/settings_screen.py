"""Settings-Dialog (erbt von BaseSettingsScreen)."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Checkbox, Input, Label, Static, TabPane
from textual_widgets import BaseSettingsScreen

from c2pa_scanner.infrastructure.settings import JsonSettingsStore


class SettingsScreen(BaseSettingsScreen):  # type: ignore[misc]
    """Einstellungen: Scan, Netzwerk (Proxy), Anzeige, plus Speicherort-Tab."""

    DEFAULT_CSS = """
    SettingsScreen .hint {
        color: $text-muted;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    """

    def app_tabs(self) -> ComposeResult:
        with TabPane("Scan", id="settings-tab-scan"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label("Min. Bildbreite (px)")
                yield Input(
                    value=str(self._settings.get("min_image_size", 0)),
                    placeholder="0",
                    id="set-min-size",
                    type="integer",
                )
            yield Static(
                "0 = aus. Sonst die Mindestbreite in Pixel: schmalere Bilder wie Icons und "
                "Thumbnails werden gar nicht erst gescannt. Fotorealistische KI-Bilder sind "
                "i.d.R. breit - ein Wert wie 300 blendet den Icon-Lärm aus.",
                classes="hint",
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
        with TabPane("Anzeige", id="settings-tab-view"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label("Bildvorschau")
                yield Checkbox(
                    "Grafische Vorschau (Sixel/TGP)",
                    value=bool(self._settings.get("graphics_preview", False)),
                    id="set-graphics",
                )
            yield Static(
                "Neustart nötig. Aus = Text-Vorschau (Halfblock), die auf jedem Terminal "
                "sicher rendert. An = pixelgenaue Vorschau, falls dein Terminal Sixel/TGP kann.",
                classes="hint",
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

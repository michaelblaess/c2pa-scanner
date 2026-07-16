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
            with Horizontal(classes="settings-row"):
                yield Label("Parallele Requests")
                yield Input(
                    value=str(self._settings.get("concurrency", 8)),
                    placeholder="8",
                    id="set-concurrency",
                    type="integer",
                )
            with Horizontal(classes="settings-row"):
                yield Label("Timeout (Sek.)")
                yield Input(
                    value=str(self._settings.get("timeout", 30)),
                    placeholder="30",
                    id="set-timeout",
                    type="integer",
                )
            with Horizontal(classes="settings-row"):
                yield Label("Browser-Rendering")
                yield Checkbox(
                    "Seiten mit Playwright rendern (Shadow-DOM/JS-Bilder)",
                    value=bool(self._settings.get("browser_render", False)),
                    id="set-render",
                )
            yield Static(
                "An = jede Seite wird zusätzlich in einem echten Chromium gerendert, um auch "
                "erst per JavaScript ins (Shadow-)DOM geladene Bilder zu finden. Gründlicher, aber "
                "deutlich langsamer. Aus = nur die Bild-URLs aus dem Server-HTML (schnell).",
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
                "sicher rendert. An = pixelgenaue Vorschau, falls Dein Terminal Sixel/TGP kann.",
                classes="hint",
            )
            with Horizontal(classes="settings-row"):
                yield Label("Seiten-Vorschau")
                yield Checkbox(
                    "Screenshot der gerenderten Seite (Playwright)",
                    value=bool(self._settings.get("page_preview", False)),
                    id="set-page-preview",
                )
            yield Static(
                "Neustart nötig. An = unter der Bildvorschau erscheint ein Screenshot der "
                "gerenderten Fundseite, zum Bild gescrollt - so siehst Du ohne Absprung, ob das "
                "KI-Label auf/am Bild dargestellt wird. Nur mit grafischer Vorschau lesbar.",
                classes="hint",
            )

    @staticmethod
    def _clamp_int(value: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(value.strip())))
        except (TypeError, ValueError):
            return default

    def collect_app_settings(self, settings: dict[str, object]) -> None:
        settings["proxy_url"] = self.query_one("#set-proxy", Input).value.strip()
        settings["graphics_preview"] = self.query_one("#set-graphics", Checkbox).value
        settings["browser_render"] = self.query_one("#set-render", Checkbox).value
        settings["page_preview"] = self.query_one("#set-page-preview", Checkbox).value
        settings["min_image_size"] = self._clamp_int(
            self.query_one("#set-min-size", Input).value, 0, 0, 100000
        )
        settings["concurrency"] = self._clamp_int(
            self.query_one("#set-concurrency", Input).value, 8, 1, 64
        )
        settings["timeout"] = self._clamp_int(
            self.query_one("#set-timeout", Input).value, 30, 5, 300
        )

    def storage_paths(self) -> list[tuple[str, Path]]:
        return [("Einstellungen", JsonSettingsStore().path)]

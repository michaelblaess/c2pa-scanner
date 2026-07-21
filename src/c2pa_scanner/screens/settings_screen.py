"""Settings-Dialog (erbt von BaseSettingsScreen)."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Checkbox, Input, Label, Select, Static, TabPane
from textual_slider import Slider
from textual_widgets import BaseSettingsScreen

from c2pa_scanner.infrastructure.settings import JsonSettingsStore

# Stufen fuer die Klartext-Beschriftung des Rate-Reglers: (Obergrenze, Text).
_RATE_STEPS: tuple[tuple[int, str], ...] = (
    (30, "sehr schonend"),
    (90, "schonend, für Produktivsysteme empfohlen"),
    (150, "zügig"),
    (10**9, "ohne Rücksicht, nur für Test-/Entwicklungssysteme"),
)


class SettingsScreen(BaseSettingsScreen):  # type: ignore[misc]
    """Einstellungen: Scan, Netzwerk (Proxy), Anzeige, plus Speicherort-Tab."""

    DEFAULT_CSS = """
    SettingsScreen .hint {
        color: $text-muted;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    SettingsScreen .rate-value {
        padding: 0 1;
    }
    SettingsScreen .rate-value.off {
        color: $text-disabled;
    }
    SettingsScreen #set-rate {
        width: 1fr;
        margin: 0 1;
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
            with Horizontal(classes="settings-row"):
                yield Label("robots.txt")
                yield Checkbox(
                    "robots.txt beachten",
                    value=bool(self._settings.get("respect_robots", True)),
                    id="set-robots",
                )
            yield Static(
                "An = per Disallow gesperrte Sitemap-Seiten werden übersprungen (die Anzahl "
                "steht im Log). Geprüft werden nur Seiten, nicht die Bilder - die liegen oft "
                "auf einer CDN-Domain mit eigener robots.txt. Aus nur für Deine eigenen Seiten "
                "sinnvoll, etwa wenn ein Testsystem pauschal alles sperrt.",
                classes="hint",
            )
            rate_on = bool(self._settings.get("rate_limit_enabled", True))
            rate_value = self._clamp_int(
                str(self._settings.get("rate_per_minute", 60)), 60, 10, 240
            )
            with Horizontal(classes="settings-row"):
                yield Label("Rate-Limit")
                yield Checkbox(
                    "Requests drosseln",
                    value=rate_on,
                    id="set-rate-on",
                )
            yield Static(
                self._rate_label(rate_value),
                id="rate-value",
                classes="rate-value" if rate_on else "rate-value off",
            )
            yield Slider(
                min=10,
                max=240,
                step=10,
                value=rate_value,
                id="set-rate",
                disabled=not rate_on,
            )
            yield Static(
                "Standardmäßig aktiv - und das aus gutem Grund. Aus = der Scanner ruft so "
                "schnell ab, wie das Ziel antwortet. Die Einstellung \"Parallele Requests\" "
                "begrenzt nur, wie viele Abrufe gleichzeitig laufen, nicht wie viele pro "
                "Minute. Bei einer großen Sitemap entstehen so schnell mehrere hundert "
                "Requests pro Minute. Kommt Browser-Rendering dazu, läuft jeder Aufruf an den "
                "Zwischenspeichern des Servers vorbei und erzeugt ein Vielfaches der Last "
                "eines normalen Besuchers. Auf einem Produktivsystem kann das die "
                "Antwortzeiten spürbar verschlechtern oder den Server an seine Speichergrenze "
                "bringen.\n\n"
                "An = Seiten, Renderings und Bilder werden gleichmäßig über die Zeit verteilt. "
                "Als Anhaltspunkt: 1.000 Seiten dauern bei 60/Minute rund 17 Minuten, bei "
                "20/Minute rund 50.\n\n"
                "Wichtig bei aktivem Browser-Rendering: gedrosselt werden die Seitenaufrufe. Was "
                "der Browser danach an Skripten, Schriften und Bildern selbst nachlädt, zählt "
                "nicht mit - die tatsächliche Last liegt dann höher als die eingestellte Zahl.",
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
        with TabPane("Export", id="settings-tab-export"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label("JIRA-Tabellenformat")
                yield Select(
                    [
                        ("Markdown (Jira Cloud)", "markdown"),
                        ("Wiki Markup (Server/DC)", "wiki"),
                    ],
                    value="wiki" if self._settings.get("jira_format") == "wiki" else "markdown",
                    allow_blank=False,
                    id="set-jira-format",
                )
            yield Static(
                "Format für den JIRA-Export (Taste j). Markdown = Jira Cloud "
                "(eon-energy.atlassian.net): eine Markdown-Tabelle wird beim Einfügen ins "
                "Kommentarfeld automatisch in eine echte Tabelle umgewandelt. Das alte Wiki "
                "Markup versteht der Cloud-Editor nicht mehr. Wiki Markup = ältere "
                "Jira-Server/Data-Center-Instanzen.",
                classes="hint",
            )

    @staticmethod
    def _clamp_int(value: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(value.strip())))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _rate_label(per_minute: int) -> str:
        """Uebersetzt die Reglerstellung in Klartext (Zahl + Einordnung)."""
        step = next(text for limit, text in _RATE_STEPS if per_minute <= limit)
        return f"{per_minute} Requests/Minute - {step}"

    @on(Slider.Changed, "#set-rate")
    def _on_rate_changed(self, event: Slider.Changed) -> None:
        """Haelt die Beschriftung ueber dem Regler am aktuellen Wert."""
        self.query_one("#rate-value", Static).update(self._rate_label(int(event.slider.value)))

    @on(Checkbox.Changed, "#set-rate-on")
    def _on_rate_toggled(self, event: Checkbox.Changed) -> None:
        """Sperrt den Regler, solange nicht gedrosselt wird."""
        enabled = bool(event.value)
        self.query_one("#set-rate", Slider).disabled = not enabled
        self.query_one("#rate-value", Static).set_class(not enabled, "off")

    def collect_app_settings(self, settings: dict[str, object]) -> None:
        settings["proxy_url"] = self.query_one("#set-proxy", Input).value.strip()
        settings["graphics_preview"] = self.query_one("#set-graphics", Checkbox).value
        settings["browser_render"] = self.query_one("#set-render", Checkbox).value
        settings["respect_robots"] = self.query_one("#set-robots", Checkbox).value
        settings["page_preview"] = self.query_one("#set-page-preview", Checkbox).value
        jira_format = self.query_one("#set-jira-format", Select).value
        settings["jira_format"] = jira_format if jira_format == "wiki" else "markdown"
        settings["min_image_size"] = self._clamp_int(
            self.query_one("#set-min-size", Input).value, 0, 0, 100000
        )
        settings["concurrency"] = self._clamp_int(
            self.query_one("#set-concurrency", Input).value, 8, 1, 64
        )
        settings["timeout"] = self._clamp_int(
            self.query_one("#set-timeout", Input).value, 30, 5, 300
        )
        settings["rate_limit_enabled"] = self.query_one("#set-rate-on", Checkbox).value
        settings["rate_per_minute"] = int(self.query_one("#set-rate", Slider).value)

    def storage_paths(self) -> list[tuple[str, Path]]:
        settings_path = JsonSettingsStore().path
        return [
            ("Einstellungen", settings_path),
            ("Zustimmung Haftungshinweis", settings_path.parent / "disclaimer.json"),
        ]

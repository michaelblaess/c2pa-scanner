"""Settings-Dialog (erbt von BaseSettingsScreen)."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Checkbox, Input, Label, Select, Static, TabPane
from textual_slider import Slider
from textual_widgets import BaseSettingsScreen

from c2pa_scanner.i18n import t
from c2pa_scanner.infrastructure.settings import JsonSettingsStore

# Stufen fuer die Klartext-Beschriftung des Rate-Reglers: (Obergrenze, Text).
_RATE_STEPS: tuple[tuple[int, str], ...] = (
    (30, "settings.rate_step_gentle"),
    (90, "settings.rate_step_careful"),
    (150, "settings.rate_step_brisk"),
    (10**9, "settings.rate_step_reckless"),
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
        with TabPane(t("settings.tab_scan"), id="settings-tab-scan"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.min_size_label"))
                yield Input(
                    value=str(self._settings.get("min_image_size", 0)),
                    placeholder="0",
                    id="set-min-size",
                    type="integer",
                )
            yield Static(t("settings.min_size_hint"), classes="hint")
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.concurrency_label"))
                yield Input(
                    value=str(self._settings.get("concurrency", 8)),
                    placeholder="8",
                    id="set-concurrency",
                    type="integer",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.timeout_label"))
                yield Input(
                    value=str(self._settings.get("timeout", 30)),
                    placeholder="30",
                    id="set-timeout",
                    type="integer",
                )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.consent_label"))
                yield Checkbox(
                    t("settings.consent_checkbox"),
                    value=bool(self._settings.get("accept_consent", True)),
                    id="set-consent",
                )
            yield Static(t("settings.consent_hint"), classes="hint")
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.render_label"))
                yield Checkbox(
                    t("settings.render_checkbox"),
                    value=bool(self._settings.get("browser_render", False)),
                    id="set-render",
                )
            yield Static(t("settings.render_hint"), classes="hint")
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.robots_label"))
                yield Checkbox(
                    t("settings.robots_checkbox"),
                    value=bool(self._settings.get("respect_robots", True)),
                    id="set-robots",
                )
            yield Static(t("settings.robots_hint"), classes="hint")
            rate_on = bool(self._settings.get("rate_limit_enabled", True))
            rate_value = self._clamp_int(
                str(self._settings.get("rate_per_minute", 60)), 60, 10, 240
            )
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.rate_label"))
                yield Checkbox(
                    t("settings.rate_checkbox"),
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
            yield Static(t("settings.rate_hint"), classes="hint")
        with (
            TabPane(t("settings.tab_network"), id="settings-tab-net"),
            VerticalScroll(),
            Horizontal(classes="settings-row"),
        ):
            yield Label(t("settings.proxy_label"))
            yield Input(
                value=str(self._settings.get("proxy_url", "")),
                placeholder=t("settings.proxy_placeholder"),
                id="set-proxy",
            )
        with TabPane(t("settings.tab_view"), id="settings-tab-view"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.graphics_label"))
                yield Checkbox(
                    t("settings.graphics_checkbox"),
                    value=bool(self._settings.get("graphics_preview", False)),
                    id="set-graphics",
                )
            yield Static(t("settings.graphics_hint"), classes="hint")
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.page_preview_label"))
                yield Checkbox(
                    t("settings.page_preview_checkbox"),
                    value=bool(self._settings.get("page_preview", False)),
                    id="set-page-preview",
                )
            yield Static(t("settings.page_preview_hint"), classes="hint")
        with TabPane(t("settings.tab_export"), id="settings-tab-export"), VerticalScroll():
            with Horizontal(classes="settings-row"):
                yield Label(t("settings.jira_format_label"))
                yield Select(
                    [
                        (t("settings.jira_format_markdown"), "markdown"),
                        (t("settings.jira_format_wiki"), "wiki"),
                    ],
                    value="wiki" if self._settings.get("jira_format") == "wiki" else "markdown",
                    allow_blank=False,
                    id="set-jira-format",
                )
            yield Static(t("settings.jira_format_hint"), classes="hint")

    @staticmethod
    def _clamp_int(value: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(value.strip())))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _rate_label(per_minute: int) -> str:
        """Uebersetzt die Reglerstellung in Klartext (Zahl + Einordnung)."""
        key = next(k for limit, k in _RATE_STEPS if per_minute <= limit)
        return t("settings.rate_value", count=per_minute, step=t(key))

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
        settings["accept_consent"] = self.query_one("#set-consent", Checkbox).value
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
            (t("settings.storage_settings"), settings_path),
            (t("settings.storage_disclaimer"), settings_path.parent / "disclaimer.json"),
        ]

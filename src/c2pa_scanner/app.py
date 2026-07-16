"""Textual-App: C2PA-/KI-Scanner ueber Sitemaps mit Bildvorschau."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header
from textual_fspicker import FileOpen, FileSave, Filters
from textual_themes import register_all
from textual_widgets import (
    AboutScreen,
    ClickableLinksMixin,
    CrashGuard,
    HorizontalSplitter,
    InfoHeader,
    InfoItem,
    LogMessage,
    LogPanel,
    LogRouter,
    UrlInputScreen,
    VerticalSplitter,
)

from c2pa_scanner import __author__, __version__, __year__
from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.infrastructure.history import HistoryEntry, HistoryStore
from c2pa_scanner.infrastructure.settings import JsonSettingsStore
from c2pa_scanner.services.sitemap_scan import SitemapScanService
from c2pa_scanner.widgets.findings_table import FindingsTable
from c2pa_scanner.widgets.preview_panel import PreviewPanel

_USER_AGENT = "Mozilla/5.0 (c2pa-scanner)"
_BAR_WIDTH = 24

_ABOUT_DESCRIPTION = (
    "Selbstprüf-Werkzeug für C2PA-/KI-Herkunft in Bildern.\n\n"
    "Es prüft die Bilder deiner EIGENEN Seiten (per Sitemap) - ausdrücklich NICHT\n"
    "zum Durchleuchten fremder Seiten oder für Abmahnungen. Der C2PA-Scan ist nur\n"
    "ein Indiz, kein Rechtsgutachten.\n\n"
    "Rechtsgrundlage: EU AI Act (VO 2024/1689), Artikel 50 - gültig ab 2. August 2026."
)


def _url_name(url: str) -> str:
    path = url.split("?")[0].split("#")[0].rstrip("/")
    return path.rsplit("/", 1)[-1] or url


def _progress_bar(done: int, total: int) -> str:
    if total <= 0:
        return "░" * _BAR_WIDTH
    filled = int(_BAR_WIDTH * done / total)
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


class C2paScannerApp(CrashGuard, ClickableLinksMixin, LogRouter, App[None]):  # type: ignore[misc]
    """Sitemap laden, Seiten crawlen, Bilder auf C2PA/KI pruefen, Bild vorschauen."""

    CSS_PATH = "app.tcss"
    TITLE = f"c2pa-scanner v{__version__}"

    BINDINGS = [
        Binding("o,O", "choose_sitemap", "URL eingeben", key_display="o",
                tooltip="Sitemap-URL eingeben (http/https)"),
        Binding("m,M", "load_sitemap_file", "Sitemap laden", key_display="m",
                tooltip="Lokale sitemap.xml öffnen"),
        Binding("c,C", "scan", "Scan", key_display="c",
                tooltip="Die aktuelle Sitemap (erneut) crawlen und Bilder prüfen"),
        Binding("h,H", "show_history", "History", key_display="h",
                tooltip="Frühere Sitemaps auswählen"),
        Binding("t,T", "make_testimage", "Testbild erzeugen", key_display="t",
                tooltip="Ein signiertes C2PA-Testbild erzeugen und speichern"),
        Binding("l,L", "toggle_log", "Log", key_display="l",
                tooltip="Log-Panel ein-/ausblenden"),
        Binding("s,S", "show_settings", "Settings", key_display="s",
                tooltip="Einstellungen öffnen (u.a. Proxy-URL)"),
        Binding("i,I", "show_about", "Info", key_display="i",
                tooltip="Über c2pa-scanner"),
        Binding("q,Q", "quit", "Beenden", key_display="q", tooltip="App beenden"),
    ]

    def __init__(self, start_sitemap: str | None = None) -> None:
        super().__init__()
        self.crash_guard_lang = "de"
        register_all(self)

        self._settings_store = JsonSettingsStore()
        settings = self._settings_store.load()
        theme = settings.get("theme")
        if isinstance(theme, str) and theme in self.available_themes:
            self.theme = theme
        self._proxy = str(settings.get("proxy_url", ""))
        self._graphics_pref = bool(settings.get("graphics_preview", False))

        last = settings.get("last_sitemap")
        self._sitemap: str | None = start_sitemap or (
            str(last) if isinstance(last, str) and last else None
        )
        self._history = HistoryStore()
        self._preview_cache: dict[str, bytes] = {}
        self._pages = 0
        self._scanning = False
        self._phase = ""
        self._prog_done = 0
        self._prog_total = 0
        self._progress_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield InfoHeader(
            [
                InfoItem("sitemap", "Sitemap", "-"),
                InfoItem("pages", "Seiten", "0"),
                InfoItem("images", "Bilder", "0"),
                InfoItem("label", "KI-Label", "0"),
                InfoItem("errors", "Fehler", "0"),
            ],
            columns=5,
            separator="  |  ",
            id="stats",
        )
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield FindingsTable(id="results")
                yield HorizontalSplitter(target_id="results", min_size=6, id="logsplit")
                yield LogPanel(lang="de", export_name="c2pa-scanner", id="log")
            yield VerticalSplitter(target_id="left", min_size=40, id="vsplit")
            yield PreviewPanel(id="preview", enabled_graphics=self._graphics_pref)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#log", LogPanel).border_title = "Log-Ausgabe"
        self._update_stats()
        if self._sitemap is not None:
            self.post_message(
                LogMessage.info(f"Sitemap geladen: {self._sitemap} - 'c' zum Scannen")
            )

    # --- Scan ---------------------------------------------------------------

    def action_scan(self) -> None:
        if self._sitemap is None:
            self.notify("Keine Sitemap - mit 'o' eine URL eingeben oder 'h' für History.",
                        severity="warning")
            return
        if self._scanning:
            return
        self._run_scan(self._sitemap)

    @work(exclusive=True)
    async def _run_scan(self, sitemap: str) -> None:
        self._scanning = True
        table = self.query_one("#results", FindingsTable)
        table.scanning = True
        table.clear_findings()
        self._pages = 0
        self._phase = "pages"
        self._prog_done = 0
        self._prog_total = 0
        self.query_one("#preview", PreviewPanel).show_bytes(None, "")
        self._update_stats()
        self.post_message(LogMessage.info(f"Scan: {sitemap}"))
        self._progress_timer = self.set_interval(0.3, self._tick_progress)

        if await self._proxy_gateway_detected(sitemap):
            self._end_scan(table)
            return

        try:
            await SitemapScanService().scan(
                sitemap,
                on_pages=self._on_pages,
                on_finding=self._on_finding,
                on_log=self._on_log,
                on_progress=self._on_progress,
                proxy=self._proxy,
            )
        except Exception as exc:  # noqa: BLE001 - Fehler dem User zeigen, nicht crashen
            self.post_message(LogMessage.error(f"Scan-Fehler: {exc}"))
            self.notify(f"Scan fehlgeschlagen: {exc}", severity="error")
            self._end_scan(table)
            return

        table.sort_now()
        findings = table.findings
        needs = sum(1 for f in findings if f.verdict.needs_label)
        errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
        self._record_history(sitemap, self._pages, len(findings), needs)
        if not findings and self._pages > 0 and not self._proxy:
            self.post_message(
                LogMessage.warning(
                    "Keine Bilder gefunden - falls die Seiten hinter einem Proxy liegen, "
                    "trage die Proxy-URL in den Einstellungen (s) ein."
                )
            )
        self.post_message(
            LogMessage.success(
                f"Fertig: {len(findings)} Bilder, {needs} Label-pflichtig, {errors} Fehler"
            )
        )
        self.notify(f"{len(findings)} Bilder, {needs} KI-Label nötig")
        self._end_scan(table)

    async def _proxy_gateway_detected(self, sitemap: str) -> bool:
        if not sitemap.lower().startswith(("http://", "https://")):
            return False
        from c2pa_scanner.infrastructure.proxy_detect import probe_proxy

        detection = await probe_proxy(sitemap, proxy=self._proxy)
        if detection is None:
            return False
        from c2pa_scanner.screens.proxy_warning import ProxyWarningScreen

        self.post_message(LogMessage.warning(f"Proxy/Gateway erkannt: {detection.host}"))
        self.push_screen(ProxyWarningScreen(detection))
        return True

    def _end_scan(self, table: FindingsTable) -> None:
        table.scanning = False
        self._scanning = False
        self._phase = ""
        if self._progress_timer is not None:
            self._progress_timer.stop()
            self._progress_timer = None
        self.sub_title = ""

    def _tick_progress(self) -> None:
        if not self._phase:
            return
        label = "Crawle Seiten" if self._phase == "pages" else "Prüfe Bilder"
        bar = _progress_bar(self._prog_done, self._prog_total)
        self.sub_title = f"{label} {bar} {self._prog_done}/{self._prog_total}"

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        self._phase = phase
        self._prog_done = done
        self._prog_total = total

    def _on_pages(self, count: int) -> None:
        self._pages = count
        self._prog_total = count
        self._update_stats()

    def _on_finding(self, finding: ImageFinding) -> None:
        self.query_one("#results", FindingsTable).add_finding(finding)
        self._update_stats()

    def _on_log(self, message: str) -> None:
        self.post_message(LogMessage.info(message))

    def _record_history(self, sitemap: str, pages: int, images: int, needs: int) -> None:
        self._history.add(
            HistoryEntry(
                sitemap=sitemap,
                at=datetime.now().strftime("%d.%m.%Y %H:%M"),  # noqa: DTZ005 - lokale Anzeige
                pages=pages,
                images=images,
                needs_label=needs,
            )
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        finding = self.query_one("#results", FindingsTable).finding_for_key(event.row_key.value)
        if finding is not None:
            self._load_preview(finding.image_url)

    @work(exclusive=True, group="preview")
    async def _load_preview(self, image_url: str) -> None:
        panel = self.query_one("#preview", PreviewPanel)
        data = self._preview_cache.get(image_url)
        if data is None:
            try:
                async with httpx.AsyncClient(
                    verify=False, follow_redirects=True, timeout=15.0,
                    headers={"User-Agent": _USER_AGENT}, proxy=self._proxy.strip() or None,
                ) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    data = response.content
            except Exception:  # noqa: BLE001 - Vorschau darf nie crashen
                data = None
            if data is not None:
                self._preview_cache[image_url] = data
        panel.show_bytes(data, _url_name(image_url))

    def _update_stats(self) -> None:
        header = self.query_one("#stats", InfoHeader)
        findings = self.query_one("#results", FindingsTable).findings
        total = len(findings)
        needs = sum(1 for f in findings if f.verdict.needs_label)
        errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
        header.set_value("sitemap", self._sitemap or "-")
        header.set_value("pages", str(self._pages))
        header.set_value("images", str(total))
        header.set_value("label", str(needs), value_style="bold red" if needs else "dim")
        header.set_value("errors", str(errors), value_style="bold red" if errors else "dim")

    # --- Sitemap-Wahl / History --------------------------------------------

    def action_choose_sitemap(self) -> None:
        self.push_screen(
            UrlInputScreen(initial=self._sitemap or "", lang="de"),
            callback=self._on_sitemap_entered,
        )

    def _on_sitemap_entered(self, url: str | None) -> None:
        if url is None:
            return
        self._sitemap = url
        self._persist({"last_sitemap": url})
        self.action_scan()

    def action_load_sitemap_file(self) -> None:
        self.push_screen(
            FileOpen(
                location=str(Path.cwd()),
                filters=Filters(
                    ("Sitemap (*.xml)", lambda p: p.suffix.lower() == ".xml"),
                    ("Alle Dateien", lambda p: True),
                ),
            ),
            callback=self._on_sitemap_file,
        )

    def _on_sitemap_file(self, path: Path | None) -> None:
        if path is None:
            return
        self._sitemap = str(path)
        self._persist({"last_sitemap": str(path)})
        self.action_scan()

    def action_show_history(self) -> None:
        from c2pa_scanner.screens.history_screen import HistoryScreen

        self.push_screen(HistoryScreen(self._history.load()), callback=self._on_history_selected)

    def _on_history_selected(self, sitemap: str | None) -> None:
        if sitemap is None:
            return
        self._sitemap = sitemap
        self._persist({"last_sitemap": sitemap})
        self.action_scan()

    # --- Testbild -----------------------------------------------------------

    def action_make_testimage(self) -> None:
        self.push_screen(
            FileSave(location=str(Path.cwd()), default_file="c2pa-testbild.jpg"),
            callback=self._on_testimage_target,
        )

    def _on_testimage_target(self, target: Path | None) -> None:
        if target is None:
            return
        self._create_testimage(Path(target))

    @work(thread=True)
    def _create_testimage(self, target: Path) -> None:
        from c2pa_scanner.infrastructure.c2pa_signer import create_test_image

        try:
            dest = create_test_image(target)
        except Exception as exc:  # noqa: BLE001 - Fehler dem User zeigen, nicht crashen
            self.call_from_thread(self.notify, f"Fehler beim Erstellen: {exc}", severity="error")
            return
        self.call_from_thread(self.post_message, LogMessage.success(f"Testbild erstellt: {dest}"))
        self.call_from_thread(self.notify, f"Testbild erstellt: {dest.name}")

    # --- Log / Settings / About --------------------------------------------

    def action_toggle_log(self) -> None:
        self.query_one("#log", LogPanel).toggle_class("hidden")
        self.query_one("#logsplit", HorizontalSplitter).toggle_class("hidden")

    def watch_theme(self, theme: str) -> None:
        if not hasattr(self, "_settings_store"):
            return
        self._persist({"theme": theme})

    def action_show_settings(self) -> None:
        from c2pa_scanner.screens.settings_screen import SettingsScreen

        self.push_screen(
            SettingsScreen(self._settings_store.load(), lang="de"),
            callback=self._on_settings_closed,
        )

    def _on_settings_closed(self, new_settings: dict[str, object] | None) -> None:
        if new_settings is None:
            return
        self._persist(new_settings)
        self._proxy = str(new_settings.get("proxy_url", self._proxy))

    def action_show_about(self) -> None:
        self.push_screen(
            AboutScreen(
                app_name="c2pa-scanner",
                version=__version__,
                author=__author__,
                release=__year__,
                description=_ABOUT_DESCRIPTION,
                license="Apache-2.0",
                lang="de",
                url="https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
            )
        )

    # --- Helpers ------------------------------------------------------------

    def _persist(self, changes: dict[str, object]) -> None:
        data = self._settings_store.load()
        data.update(changes)
        self._settings_store.save(data)

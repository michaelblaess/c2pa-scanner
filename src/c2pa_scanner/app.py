"""Textual-App: C2PA-/KI-Scanner ueber Sitemaps mit Bildvorschau."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from datetime import datetime
from pathlib import Path

import httpx
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual_fspicker import FileOpen, FileSave, Filters
from textual_themes import register_all
from textual_widgets import (
    AboutScreen,
    ClickableLinksMixin,
    ContextMenuItem,
    ContextMenuScreen,
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
from c2pa_scanner.widgets.findings_table import FindingsTable, ResultsDataTable
from c2pa_scanner.widgets.preview_panel import PreviewPanel

_USER_AGENT = "Mozilla/5.0 (c2pa-scanner)"
_BAR_WIDTH = 24

_ABOUT_DESCRIPTION = (
    "Prüft Bilder auf ihre C2PA-/KI-Herkunft.\n\n"
    "Es prüft die Bilder Deiner EIGENEN Seiten (per Sitemap) - ausdrücklich NICHT\n"
    "zum Durchleuchten fremder Seiten oder für Abmahnungen. Der C2PA-Scan ist nur\n"
    "ein Indiz, kein Rechtsgutachten.\n\n"
    "Status-Kategorien in der Tabelle:\n"
    "  KI-generiert   - Bild vollständig von einer KI erzeugt\n"
    "  KI-bearbeitet  - echtes Material mit KI kombiniert oder verändert\n"
    "                   (z.B. generativer Fill, Composite aus echt + KI)\n"
    "  C2PA (kein KI) - Herkunft signiert, aber ohne KI-Marker (z.B. Kamera)\n"
    "  kein C2PA      - keine Herkunftsdaten im Bild gefunden\n\n"
    "KI-generiert und KI-bearbeitet sind beide kennzeichnungspflichtig; die\n"
    "Unterscheidung sagt nur, wie stark KI im Spiel war (IPTC digitalSourceType).\n\n"
    "Wichtig: Der Scan ist ein positives Indiz FÜR KI (wenn ein Marker da ist),\n"
    "aber kein Beweis dagegen. Fehlt der Marker oder ganz das C2PA-Manifest,\n"
    "kann trotzdem KI benutzt worden sein - Herkunftsdaten zeigen nur, was das\n"
    "signierende Tool eingetragen hat.\n\n"
    "Rechtsgrundlage: EU AI Act (VO 2024/1689), Artikel 50 - gültig ab 2. August 2026.\n"
    "Gesetzestext: https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
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
        Binding("e,E", "toggle_ai", "Nur KI-Bilder", key_display="e",
                tooltip="Nur KI-Bilder anzeigen / alle anzeigen"),
        Binding("d,D", "c2pa_details", "C2PA-Details", key_display="d",
                tooltip="Das rohe C2PA-Manifest des markierten Bildes als Dialog anzeigen"),
        Binding("h,H", "show_history", "History", key_display="h",
                tooltip="Frühere Sitemaps auswählen"),
        Binding("slash", "focus_filter", "Filter", key_display="/", show=False,
                tooltip="Filter-Eingabe fokussieren"),
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
        self._render = bool(settings.get("browser_render", False))
        self._min_size = max(0, self._read_int(settings, "min_image_size", 0))
        self._concurrency = max(1, self._read_int(settings, "concurrency", 8))
        self._timeout = max(1, self._read_int(settings, "timeout", 30))

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
        self._scan_start = datetime.now()  # noqa: DTZ005 - nur Dauer-Differenz
        self._attention_on = False
        self._current_finding: ImageFinding | None = None
        self._export_content = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield InfoHeader(
            [
                InfoItem("pages", "Seiten", "0"),
                InfoItem("images", "Bilder", "0"),
                InfoItem("label", "KI-Bilder", "0"),
                InfoItem("errors", "Fehler", "0"),
            ],
            columns=4,
            title="Sitemap: -",
            separator="  |  ",
            id="stats",
        )
        with Horizontal(id="main"):
            yield FindingsTable(id="results")
            yield VerticalSplitter(target_id="results", min_size=30, id="vsplit")
            yield PreviewPanel(id="preview", enabled_graphics=self._graphics_pref)
        yield HorizontalSplitter(target_id="main", min_size=8, id="logsplit")
        yield LogPanel(lang="de", export_name="c2pa-scanner", id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#log", LogPanel).border_title = " Log-Ausgabe "
        self._update_stats()
        # Fokus auf die Tabelle, NICHT auf die Suchleiste - ein fokussiertes
        # Text-Input wuerde die Buchstaben-Shortcuts aus dem Footer ausblenden.
        self.call_after_refresh(self._focus_table)
        # Footer-Taste blinken lassen, die als naechstes dran ist (o bzw. c).
        self.set_interval(0.6, self._tick_attention)
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
        self._scan_start = datetime.now()  # noqa: DTZ005 - nur Dauer-Differenz
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

        resolved = sitemap
        def on_resolved(url: str) -> None:
            nonlocal resolved
            resolved = url
            # Discovery hat eine andere Sitemap gefunden -> Header sofort umziehen.
            if url != sitemap:
                self._sitemap = url
                self._update_stats()

        try:
            await SitemapScanService(
                page_concurrency=self._concurrency,
                image_concurrency=self._concurrency,
                timeout=float(self._timeout),
            ).scan(
                sitemap,
                on_pages=self._on_pages,
                on_finding=self._on_finding,
                on_log=self._on_log,
                on_progress=self._on_progress,
                on_resolved=on_resolved,
                proxy=self._proxy,
                min_image_size=self._min_size,
                render=self._render,
            )
        except Exception as exc:  # noqa: BLE001 - Fehler dem User zeigen, nicht crashen
            self.post_message(LogMessage.error(f"Scan-Fehler: {exc}"))
            self.notify(f"Scan fehlgeschlagen: {exc}", severity="error")
            self._end_scan(table)
            return

        # Sitemap hat sauber geladen (kein 404/Parse-Fehler) -> erst JETZT als
        # zuletzt erfolgreiche Quelle merken, nicht schon beim Eingeben. Bei
        # Auto-Discovery die tatsaechlich gefundene URL statt der Eingabe.
        self._persist({"last_sitemap": resolved})
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

        from c2pa_scanner.screens.scan_summary import ScanSummaryScreen

        c2pa = sum(1 for f in findings if f.has_c2pa)
        duration = (datetime.now() - self._scan_start).total_seconds()  # noqa: DTZ005
        self.push_screen(
            ScanSummaryScreen(
                sitemap=sitemap,
                pages=self._pages,
                images=len(findings),
                c2pa=c2pa,
                ai_label=needs,
                errors=errors,
                duration_s=duration,
            )
        )

    async def _proxy_gateway_detected(self, sitemap: str) -> bool:
        if not sitemap.lower().startswith(("http://", "https://")):
            return False
        from c2pa_scanner.infrastructure.proxy_detect import probe_proxy

        detection = await probe_proxy(sitemap, proxy=self._proxy, timeout=float(self._timeout))
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
        self._current_finding = finding
        # Waehrend des Scans keine Bilder laden (spart Bandbreite; Vorschau nach dem Scan).
        if self._scanning:
            return
        if finding is not None:
            self._load_preview(finding.image_url, finding.page_url)

    @work(exclusive=True, group="preview")
    async def _load_preview(self, image_url: str, page_url: str) -> None:
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
        panel.show_bytes(data, _url_name(image_url), page_url)

    def action_c2pa_details(self) -> None:
        finding = self._current_finding
        if finding is None:
            self.notify("Keine Zeile markiert.", severity="warning")
            return
        self._show_c2pa_details(finding.image_url, _url_name(finding.image_url))

    @work(exclusive=True, group="c2pa")
    async def _show_c2pa_details(self, image_url: str, title: str) -> None:
        from c2pa_scanner.infrastructure.c2pa_reader import read_manifest_json
        from c2pa_scanner.screens.c2pa_details import C2paDetailsScreen

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
            except Exception:  # noqa: BLE001 - Fehler im Dialog anzeigen
                data = None
            if data is not None:
                self._preview_cache[image_url] = data
        manifest = (
            await asyncio.to_thread(read_manifest_json, data, "") if data is not None else None
        )
        self.push_screen(C2paDetailsScreen(title=title, manifest_json=manifest))

    def _update_stats(self) -> None:
        header = self.query_one("#stats", InfoHeader)
        findings = self.query_one("#results", FindingsTable).findings
        total = len(findings)
        needs = sum(1 for f in findings if f.verdict.needs_label)
        errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
        self._set_sitemap_title(header)
        header.set_value("pages", str(self._pages))
        header.set_value("images", str(total))
        header.set_value("label", str(needs), value_style="bold red" if needs else "dim")
        header.set_value("errors", str(errors), value_style="bold red" if errors else "dim")

    # --- Sitemap-Wahl / History --------------------------------------------

    def action_choose_sitemap(self) -> None:
        # Nur eine echte http(s)-URL vorbefuellen - ein lokaler Dateipfad (per
        # 'm' geladen) waere hier ungueltig und darf nicht ins URL-Feld.
        current = self._sitemap or ""
        initial = current if current.lower().startswith(("http://", "https://")) else ""
        self.push_screen(
            UrlInputScreen(initial=initial, lang="de"),
            callback=self._on_sitemap_entered,
        )

    def _on_sitemap_entered(self, url: str | None) -> None:
        if url is None:
            return
        self._sitemap = url
        self._sitemap_loaded()

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
        self._sitemap_loaded()

    def action_show_history(self) -> None:
        from c2pa_scanner.screens.history_screen import HistoryScreen

        self.push_screen(HistoryScreen(self._history.load()), callback=self._on_history_selected)

    def _on_history_selected(self, sitemap: str | None) -> None:
        if sitemap is None:
            return
        self._sitemap = sitemap
        self._sitemap_loaded()

    def _sitemap_loaded(self) -> None:
        # Sitemap uebernommen, aber NICHT automatisch scannen - die Footer-Taste
        # 'c' blinkt (via _tick_attention) und der User startet selbst.
        if self._scanning:
            return
        self._pages = 0
        self._current_finding = None
        self.query_one("#results", FindingsTable).clear_findings()
        with contextlib.suppress(Exception):
            self.query_one("#preview", PreviewPanel).show_bytes(None, "")
        self._update_stats()
        self.post_message(
            LogMessage.info(f"Sitemap geladen: {self._sitemap} - 'c' zum Scannen")
        )

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

    def action_toggle_ai(self) -> None:
        table = self.query_one("#results", FindingsTable)
        new_state = not table.only_ai()
        table.set_only_ai(new_state)
        # Binding-Label spiegelt die naechste moegliche Aktion.
        label = "Alle anzeigen" if new_state else "Nur KI-Bilder"
        for key, bindings in self._bindings.key_to_bindings.items():
            for i, binding in enumerate(bindings):
                if binding.action == "toggle_ai":
                    self._bindings.key_to_bindings[key][i] = dataclasses.replace(
                        binding, description=label
                    )
        self.refresh_bindings()
        self.notify("Nur KI-Bilder" if new_state else "Alle Bilder")

    # --- Kontextmenue / Export ---------------------------------------------

    def on_results_data_table_right_clicked(
        self, event: ResultsDataTable.RightClicked
    ) -> None:
        table = self.query_one("#results", FindingsTable)
        only_ai = table.only_ai()
        has_rows = bool(table.shown_findings())
        has_current = self._current_finding is not None
        items = [
            ContextMenuItem("export_json", "Export JSON", enabled=has_rows),
            ContextMenuItem("export_jira", "Export JIRA-Tabelle", enabled=has_rows),
            ContextMenuItem("export_clip", "Export Zwischenablage (Text)", enabled=has_rows),
            ContextMenuItem.separator(),
            ContextMenuItem("toggle_ai", "Alle anzeigen" if only_ai else "Nur KI-Bilder"),
            ContextMenuItem("c2pa_details", "C2PA-Details anzeigen", enabled=has_current),
        ]
        self.push_screen(
            ContextMenuScreen(items, at=(event.x, event.y)),
            callback=self._on_context_menu,
        )

    def _on_context_menu(self, action_id: str | None) -> None:
        actions = {
            "export_json": self.action_export_json,
            "export_jira": self.action_export_jira,
            "export_clip": self.action_export_clip,
            "toggle_ai": self.action_toggle_ai,
            "c2pa_details": self.action_c2pa_details,
        }
        handler = actions.get(action_id or "")
        if handler is not None:
            handler()

    def _shown_findings(self) -> list[ImageFinding]:
        return self.query_one("#results", FindingsTable).shown_findings()

    def action_export_json(self) -> None:
        if not self._shown_findings():
            self.notify("Nichts zu exportieren.", severity="warning")
            return
        self.push_screen(
            FileSave(location=str(Path.cwd()), default_file="c2pa-findings.json"),
            callback=self._on_export_json_target,
        )

    def _on_export_json_target(self, target: Path | None) -> None:
        if target is None:
            return
        from c2pa_scanner.services.export import build_json

        content = build_json(self._shown_findings())
        try:
            Path(target).write_text(content, encoding="utf-8")
        except OSError as exc:
            self.notify(f"Speichern fehlgeschlagen: {exc}", severity="error")
            return
        self.post_message(LogMessage.success(f"JSON-Export: {target}"))
        self.notify(f"Exportiert: {Path(target).name}")

    def action_export_jira(self) -> None:
        findings = self._shown_findings()
        if not findings:
            self.notify("Nichts zu exportieren.", severity="warning")
            return
        from c2pa_scanner.services.export import build_jira

        self.copy_to_clipboard(build_jira(findings))
        self.notify(f"{len(findings)} Zeilen als JIRA-Tabelle kopiert")

    def action_export_clip(self) -> None:
        findings = self._shown_findings()
        if not findings:
            self.notify("Nichts zu exportieren.", severity="warning")
            return
        from c2pa_scanner.services.export import build_text

        self.copy_to_clipboard(build_text(findings))
        self.notify(f"{len(findings)} Zeilen als Text kopiert")

    def action_focus_filter(self) -> None:
        with contextlib.suppress(Exception):  # Fokus ist unkritisch
            self.query_one("#filter-bar", Input).focus()

    def _focus_table(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#results-data", DataTable).focus()

    def _tick_attention(self) -> None:
        # Welche Footer-Taste soll Aufmerksamkeit ziehen? o (Sitemap waehlen)
        # solange keine da ist, danach c (Scan) bis zum ersten Scan.
        if self._sitemap is None:
            target = "choose_sitemap"
        elif not self._scanning and not self.query_one("#results", FindingsTable).findings:
            target = "scan"
        else:
            target = ""
        self._attention_on = not self._attention_on if target else False
        for action in ("choose_sitemap", "scan"):
            key = self._footer_key(action)
            if key is not None:
                key.set_class(action == target and self._attention_on, "-attention")

    def _footer_key(self, action: str) -> Widget | None:
        with contextlib.suppress(Exception):
            for footer_key in self.query("FooterKey"):
                if getattr(footer_key, "action", "") == action:
                    return footer_key
        return None

    def on_key(self, event: events.Key) -> None:
        # Esc im Filterfeld gibt den Fokus zurueck an die Tabelle -> Footer wieder voll.
        focused = self.focused
        if event.key == "escape" and isinstance(focused, Input) and focused.id == "filter-bar":
            event.stop()
            self.call_after_refresh(self._focus_table)

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
        self._min_size = max(0, self._read_int(new_settings, "min_image_size", self._min_size))
        self._concurrency = max(1, self._read_int(new_settings, "concurrency", self._concurrency))
        self._timeout = max(1, self._read_int(new_settings, "timeout", self._timeout))

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
                url="https://www.michaelblaess.de/",
                homepage_url="https://github.com/michaelblaess/c2pa-scanner",
            )
        )

    # --- Helpers ------------------------------------------------------------

    @staticmethod
    def _display_sitemap(sitemap: str | None) -> str:
        if not sitemap:
            return "-"
        # Die Titelzeile spannt die volle Header-Breite - grosszuegiger Schwellwert.
        if len(sitemap) <= 80:
            return sitemap
        # Zu lang -> nur den Dateinamen/letztes Segment (Pfad ODER URL).
        name = sitemap.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return name or sitemap

    def _set_sitemap_title(self, header: InfoHeader) -> None:
        # Sitemap steht in der vollbreiten Titelzeile (kein Spalten-Clipping);
        # der volle Wert haengt zusaetzlich als Tooltip an der Titelzeile.
        text = f"Sitemap: {self._display_sitemap(self._sitemap)}"
        with contextlib.suppress(Exception):
            title = header.query_one("#info-title", Static)
            title.update(text)
            title.tooltip = self._sitemap or None

    @staticmethod
    def _read_int(settings: dict[str, object], key: str, default: int) -> int:
        try:
            return int(str(settings.get(key, default) or default))
        except (TypeError, ValueError):
            return default

    def _persist(self, changes: dict[str, object]) -> None:
        data = self._settings_store.load()
        data.update(changes)
        self._settings_store.save(data)

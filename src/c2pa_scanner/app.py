"""Textual-App: C2PA-/KI-Scanner ueber Sitemaps mit Bildvorschau."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import traceback
from datetime import datetime
from pathlib import Path

import httpx
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual_fspicker import FileOpen, FileSave, Filters
from textual_themes import register_all
from textual_widgets import (
    DISCLAIMER_VERSION,
    AboutScreen,
    ClickableLinksMixin,
    ContextMenuItem,
    ContextMenuScreen,
    CrashGuard,
    DisclaimerScreen,
    DisclaimerStore,
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
from c2pa_scanner.i18n import current_language, t
from c2pa_scanner.infrastructure.asyncio_guard import install_playwright_shutdown_guard
from c2pa_scanner.infrastructure.c2pa_reader import (
    C2paUnavailableError,
    ensure_c2pa_available,
)
from c2pa_scanner.infrastructure.history import HistoryEntry, HistoryStore
from c2pa_scanner.infrastructure.settings import CRASH_LOG_NAME, JsonSettingsStore
from c2pa_scanner.services.preview_service import PreviewService
from c2pa_scanner.services.sitemap_scan import SitemapScanService
from c2pa_scanner.widgets.findings_table import FindingsTable, ResultsDataTable
from c2pa_scanner.widgets.preview_panel import PreviewPanel

_USER_AGENT = "Mozilla/5.0 (c2pa-scanner)"
_BAR_WIDTH = 24



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

    # Die Beschriftungen stehen hier nur als Platzhalter: BINDINGS wird beim
    # Import der Klasse ausgewertet, also bevor eine Sprache geladen ist. Die
    # uebersetzten Texte setzt _init_bindings() zur Laufzeit.
    BINDINGS = [
        Binding("o,O", "choose_sitemap", "placeholder", key_display="o"),
        Binding("m,M", "load_sitemap_file", "placeholder", key_display="m"),
        Binding("c,C", "scan", "placeholder", key_display="c"),
        # Nur waehrend eines Laufs im Fusszeilenmenue - siehe check_action.
        Binding("x,X", "cancel_scan", "placeholder", key_display="x"),
        Binding("e,E", "toggle_ai", "placeholder", key_display="e"),
        Binding("d,D", "c2pa_details", "placeholder", key_display="d"),
        Binding("h,H", "show_history", "placeholder", key_display="h"),
        Binding("slash", "focus_filter", "placeholder", key_display="/", show=False),
        Binding("t,T", "make_testimage", "placeholder", key_display="t"),
        Binding("l,L", "toggle_log", "placeholder", key_display="l"),
        Binding("s,S", "show_settings", "placeholder", key_display="s"),
        Binding("i,I", "show_about", "placeholder", key_display="i"),
        Binding("q,Q", "quit", "placeholder", key_display="q"),
    ]

    def __init__(self, start_sitemap: str | None = None) -> None:
        super().__init__()
        self.crash_guard_lang = current_language()
        register_all(self)

        self._settings_store = JsonSettingsStore()
        # Zustimmung zum Haftungshinweis liegt neben den Einstellungen.
        self._disclaimer = DisclaimerStore(
            JsonSettingsStore().path.parent / "disclaimer.json"
        )
        settings = self._settings_store.load()
        theme = settings.get("theme")
        if isinstance(theme, str) and theme in self.available_themes:
            self.theme = theme
        self._proxy = str(settings.get("proxy_url", ""))
        self._graphics_pref = bool(settings.get("graphics_preview", False))
        self._render = bool(settings.get("browser_render", False))
        self._respect_robots = bool(settings.get("respect_robots", True))
        # Cookie-Banner blockieren die Vorschau und halten auf gerenderten Seiten
        # Bilder zurueck - darum standardmaessig zustimmen.
        self._accept_consent = bool(settings.get("accept_consent", True))
        self._page_preview = bool(settings.get("page_preview", False))
        self._jira_format = str(settings.get("jira_format", "markdown"))
        self._min_size = max(0, self._read_int(settings, "min_image_size", 0))
        self._concurrency = max(1, self._read_int(settings, "concurrency", 8))
        self._timeout = max(1, self._read_int(settings, "timeout", 30))
        # Standardmaessig gedrosselt: ungebremst kann ein Lauf ein Produktivsystem
        # spuerbar belasten. Wer schneller sein will, schaltet es bewusst ab.
        self._rate_limit_on = bool(settings.get("rate_limit_enabled", True))
        self._rate_per_minute = max(1, self._read_int(settings, "rate_per_minute", 60))

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
        self._preview_service: PreviewService | None = None
        self._scan_service: SitemapScanService | None = None

        self._init_bindings()

    def _init_bindings(self) -> None:
        """Setzt die uebersetzten Beschriftungen und Tooltips aller Tastenkuerzel."""
        labels = {
            "choose_sitemap": "binding.choose_sitemap",
            "load_sitemap_file": "binding.load_sitemap_file",
            "scan": "binding.scan",
            "cancel_scan": "binding.cancel_scan",
            "toggle_ai": "binding.toggle_ai",
            "c2pa_details": "binding.c2pa_details",
            "show_history": "binding.history",
            "focus_filter": "binding.filter",
            "make_testimage": "binding.make_testimage",
            "toggle_log": "binding.toggle_log",
            "show_settings": "binding.settings",
            "show_about": "binding.about",
            "quit": "binding.quit",
        }
        for key, bindings_list in self._bindings.key_to_bindings.items():
            for i, binding in enumerate(bindings_list):
                base = labels.get(binding.action)
                if base is None:
                    continue
                self._bindings.key_to_bindings[key][i] = dataclasses.replace(
                    binding,
                    description=t(base),
                    tooltip=t(f"{base}_tip"),
                )

    def compose(self) -> ComposeResult:
        yield Header()
        yield InfoHeader(
            [
                InfoItem("pages", t("stats.pages"), "0"),
                InfoItem("images", t("stats.images"), "0"),
                InfoItem("label", t("stats.ai"), "0"),
                InfoItem("errors", t("stats.errors"), "0"),
            ],
            columns=4,
            title=t("app.subtitle_none"),
            separator="  |  ",
            id="stats",
        )
        with Horizontal(id="main"):
            yield FindingsTable(id="results")
            yield VerticalSplitter(target_id="results", min_size=30, id="vsplit")
            with Vertical(id="preview-col"):
                yield PreviewPanel(id="preview", enabled_graphics=self._graphics_pref)
                yield HorizontalSplitter(
                    target_id="preview", min_size=6, id="preview-split",
                    classes="" if self._page_preview else "hidden",
                )
                yield PreviewPanel(
                    id="page-preview", enabled_graphics=self._graphics_pref,
                    classes="" if self._page_preview else "hidden",
                )
        yield HorizontalSplitter(target_id="main", min_size=8, id="logsplit")
        yield LogPanel(lang=current_language(), export_name="c2pa-scanner", id="log")
        yield Footer()

    def on_mount(self) -> None:
        # Verwaiste Playwright-Futures beim Beenden abfangen (Sidecar/Renderer).
        install_playwright_shutdown_guard(asyncio.get_running_loop())
        self.query_one("#log", LogPanel).border_title = t("app.log_title")
        self._update_stats()
        self._log_theme()
        # Fokus auf die Tabelle, NICHT auf die Suchleiste - ein fokussiertes
        # Text-Input wuerde die Buchstaben-Shortcuts aus dem Footer ausblenden.
        self.call_after_refresh(self._focus_table)
        # Footer-Taste blinken lassen, die als naechstes dran ist (o bzw. c).
        self.set_interval(0.6, self._tick_attention)
        if self._sitemap is not None:
            self.post_message(
                LogMessage.info(t("log.sitemap_loaded", sitemap=self._sitemap))
            )
        self._ask_disclaimer()

    def _handle_exception(self, error: Exception) -> None:
        """Schreibt den Traceback auf Platte, bevor der Fehlerdialog laeuft.

        Der CrashGuard zeigt den Traceback nur im Dialog an. Faellt dieser beim
        Neuaufbau selbst mit (struktureller Defekt), geht der Bericht verloren und
        der naechste Absturz ist wieder undiagnostizierbar - unter Windows bleibt
        dann nur Maus-Steuerzeichen-Muell im Terminal zurueck. Die Datei ueberlebt
        auch den harten Absturzpfad von Textual.
        """
        with contextlib.suppress(Exception):
            self._persist_crash(error)
        super()._handle_exception(error)

    def _persist_crash(self, error: BaseException) -> None:
        """Haengt den Traceback mit Zeitstempel an die Absturz-Datei an."""
        report = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        path = self._settings_store.path.parent / CRASH_LOG_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 - lokale Zeit
        header = f"\n===== {stamp} - c2pa-scanner v{__version__} =====\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(header + report)

    def _ask_disclaimer(self) -> None:
        """Holt den Haftungshinweis ein, solange er nicht (in dieser Fassung) bestaetigt ist."""
        if self._disclaimer.accepted_version == DISCLAIMER_VERSION:
            return
        self.push_screen(
            DisclaimerScreen(
                app_name=f"c2pa-scanner {__version__}",
                lang=current_language(),
                author=__author__,
                footer=f"© {__year__} {__author__} · github.com/michaelblaess/c2pa-scanner",
            ),
            callback=self._on_disclaimer,
        )

    def _on_disclaimer(self, accepted: bool | None) -> None:
        """Ohne Zustimmung wird das Programm beendet - der Hinweis ist nicht optional."""
        if not accepted:
            self.exit()
            return
        self._disclaimer.record()

    async def on_unmount(self) -> None:
        # Laufende Vorschau-Worker zuerst abbrechen, damit sie das capture()-Lock
        # freigeben, dann den Sidecar-Browser sauber schliessen. Sonst faellt
        # close() mitten in einen offenen Screenshot-Call.
        with contextlib.suppress(Exception):
            self.workers.cancel_group(self, "page-preview")
        if self._preview_service is not None:
            await self._preview_service.close()

    # --- Scan ---------------------------------------------------------------

    def action_scan(self) -> None:
        if self._sitemap is None:
            self.notify(t("notify.no_sitemap"),
                        severity="warning")
            return
        if self._scanning:
            return
        self._run_scan(self._sitemap)

    @work(exclusive=True)
    async def _run_scan(self, sitemap: str) -> None:
        self._scanning = True
        self.refresh_bindings()  # 'x Scan abbrechen' einblenden, 'c' ausblenden
        self._scan_start = datetime.now()  # noqa: DTZ005 - nur Dauer-Differenz
        table = self.query_one("#results", FindingsTable)
        table.scanning = True
        table.clear_findings()
        self._pages = 0
        self._phase = "pages"
        self._prog_done = 0
        self._prog_total = 0
        self.query_one("#preview", PreviewPanel).show_bytes(None, "")
        self.query_one("#page-preview", PreviewPanel).show_bytes(None, "")
        self._update_stats()
        self.post_message(LogMessage.info(t("log.scan_start", sitemap=sitemap)))
        self._progress_timer = self.set_interval(0.3, self._tick_progress)

        # Fehlt die native Bibliothek, waere JEDES Ergebnis still falsch-negativ
        # ("kein C2PA" fuer alles). Darum hier hart abbrechen, statt pro Bild einen
        # RuntimeError zu melden, der im Log untergeht.
        try:
            ensure_c2pa_available()
        except C2paUnavailableError as exc:
            self.post_message(LogMessage.error(t("log.c2pa_unavailable", error=exc)))
            self.post_message(
                LogMessage.error(t("log.scan_aborted"))
            )
            self.notify(
                t("notify.c2pa_missing"),
                severity="error",
                timeout=10,
            )
            self._end_scan(table)
            return

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

        service = SitemapScanService(
            page_concurrency=self._concurrency,
            image_concurrency=self._concurrency,
            timeout=float(self._timeout),
            rate_per_minute=self._rate_per_minute if self._rate_limit_on else 0,
        )
        self._scan_service = service
        try:
            await service.scan(
                sitemap,
                on_pages=self._on_pages,
                on_finding=self._on_finding,
                on_log=self._on_log,
                on_progress=self._on_progress,
                on_resolved=on_resolved,
                proxy=self._proxy,
                min_image_size=self._min_size,
                render=self._render,
                respect_robots=self._respect_robots,
                accept_consent=self._accept_consent,
            )
        except Exception as exc:  # noqa: BLE001 - Fehler dem User zeigen, nicht crashen
            self.post_message(LogMessage.error(t("log.scan_error", error=exc)))
            self.notify(t("notify.scan_failed", error=exc), severity="error")
            self._end_scan(table)
            return

        # Abgebrochen: die bis hierher gefundenen Zeilen bleiben stehen, damit man
        # sie ansehen kann. Kein Verlaufseintrag und keine Zusammenfassung - beide
        # wuerden ein unvollstaendiges Ergebnis wie ein vollstaendiges aussehen lassen.
        if service.cancelled:
            table.sort_now()
            findings = table.findings
            self.post_message(
                LogMessage.warning(t("log.scan_cancelled_summary", count=len(findings)))
            )
            self.notify(t("notify.scan_cancelled", count=len(findings)), severity="warning")
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
        self.notify(t("notify.scan_done", count=len(findings), needs=needs))
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

        self.post_message(LogMessage.warning(t("log.proxy_detected", host=detection.host)))
        self.push_screen(ProxyWarningScreen(detection))
        return True

    def action_cancel_scan(self) -> None:
        """Bricht den laufenden Scan ab; die bisherigen Treffer bleiben stehen."""
        service = self._scan_service
        if not self._scanning or service is None:
            self.notify(t("notify.no_scan_active"), severity="warning")
            return
        if service.cancelled:  # schon angefordert - der Lauf ebbt gerade ab
            return
        service.cancel()
        self.post_message(LogMessage.warning(t("log.cancel_requested")))
        self.notify(t("notify.scan_cancelling"))
        self.sub_title = t("progress.cancelling")
        self._phase = ""  # der Fortschrittsbalken soll nicht weiterlaufen
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Modale Dialoge: keine App-Tasten anbieten, solange einer offen ist.
        if len(self.screen_stack) > 1:
            return None
        # Abbrechen nur waehrend eines Laufs, Scannen nur ausserhalb.
        if action == "cancel_scan":
            return True if self._scanning else None
        if action == "scan" and self._scanning:
            return None
        return True

    def _end_scan(self, table: FindingsTable) -> None:
        table.scanning = False
        self._scanning = False
        self._scan_service = None
        self._phase = ""
        if self._progress_timer is not None:
            self._progress_timer.stop()
            self._progress_timer = None
        self.sub_title = ""
        self.refresh_bindings()

    def _tick_progress(self) -> None:
        if not self._phase:
            return
        label = t("progress.pages") if self._phase == "pages" else t("progress.images")
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
            if self._page_preview:
                self._load_page_preview(finding.page_url, finding.image_url)

    @work(exclusive=True, group="page-preview")
    async def _load_page_preview(self, page_url: str, image_url: str) -> None:
        panel = self.query_one("#page-preview", PreviewPanel)
        if self._preview_service is None:
            self._preview_service = PreviewService(
                proxy=self._proxy, accept_consent=self._accept_consent
            )
        phases = {
            "navigate": "Seite laden ...",
            "consent": "Cookie-Banner ...",
            "render": "Rendern ...",
            "capture": "Screenshot ...",
        }

        def on_phase(phase: str) -> None:
            panel.show_bytes(None, f"Bitte warten - {phases.get(phase, phase)}", page_url)

        panel.show_bytes(None, "Bitte warten ...", page_url)
        data = await self._preview_service.capture(page_url, image_url, on_phase=on_phase)
        panel.show_bytes(data, "" if data else "Vorschau fehlgeschlagen", page_url)

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
            self.notify(t("notify.no_row"), severity="warning")
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
            UrlInputScreen(initial=initial, lang=current_language()),
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
            self.query_one("#page-preview", PreviewPanel).show_bytes(None, "")
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
        self.call_from_thread(
            self.post_message, LogMessage.success(t("log.testimage_created", path=dest))
        )
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
        self.notify(t("notify.only_ai") if new_state else t("notify.all_images"))

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
            self.notify(t("notify.nothing_to_export"), severity="warning")
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
            self.notify(t("notify.save_failed", error=exc), severity="error")
            return
        self.post_message(LogMessage.success(t("log.json_export", path=target)))
        self.notify(t("notify.exported", name=Path(target).name))

    def action_export_jira(self) -> None:
        findings = self._shown_findings()
        if not findings:
            self.notify(t("notify.nothing_to_export"), severity="warning")
            return
        from c2pa_scanner.services.export import build_jira

        self.copy_to_clipboard(build_jira(findings, self._jira_format))
        label = "Wiki" if self._jira_format.lower() == "wiki" else "Markdown"
        self.notify(t("notify.jira_copied", count=len(findings), format=label))

    def action_export_clip(self) -> None:
        findings = self._shown_findings()
        if not findings:
            self.notify(t("notify.nothing_to_export"), severity="warning")
            return
        from c2pa_scanner.services.export import build_text

        self.copy_to_clipboard(build_text(findings))
        self.notify(t("notify.text_copied", count=len(findings)))

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
        self._log_theme()

    def _log_theme(self) -> None:
        """Meldet das aktive Theme im Log.

        Textual zeigt nirgends an, welches Theme gerade laeuft - nach einem
        Neustart weiss man also nicht, was man vor sich hat. Der technische
        Name steht mit dabei, weil genau der in den Einstellungen und in der
        Befehlspalette auftaucht.
        """
        with contextlib.suppress(Exception):
            from textual_themes import THEME_DISPLAY_NAMES

            name = self.theme or ""
            anzeige = THEME_DISPLAY_NAMES.get(name, name)
            beschriftung = f"{anzeige} ({name})" if anzeige != name else name
            self.post_message(LogMessage.info(t("log.theme_active", name=beschriftung)))

    def action_show_settings(self) -> None:
        from c2pa_scanner.screens.settings_screen import SettingsScreen

        self.push_screen(
            SettingsScreen(self._settings_store.load(), lang=current_language()),
            callback=self._on_settings_closed,
        )

    def _on_settings_closed(self, new_settings: dict[str, object] | None) -> None:
        if new_settings is None:
            return
        self._persist(new_settings)
        old_proxy, old_consent = self._proxy, self._accept_consent
        self._proxy = str(new_settings.get("proxy_url", self._proxy))
        self._accept_consent = bool(new_settings.get("accept_consent", self._accept_consent))
        # Der Vorschau-Browser wird einmal gestartet und offen gehalten; Proxy und
        # Consent-Verhalten stecken in dieser Instanz. Bei Aenderung also verwerfen,
        # sonst arbeitet die Vorschau bis zum Neustart mit den alten Werten weiter.
        if (old_proxy, old_consent) != (self._proxy, self._accept_consent):
            self._reset_preview_service()
        self._min_size = max(0, self._read_int(new_settings, "min_image_size", self._min_size))
        self._concurrency = max(1, self._read_int(new_settings, "concurrency", self._concurrency))
        self._timeout = max(1, self._read_int(new_settings, "timeout", self._timeout))
        self._jira_format = str(new_settings.get("jira_format", self._jira_format))
        # Scan-Parameter sofort uebernehmen: sie werden erst beim naechsten Scan
        # gelesen, muessen also nicht auf einen App-Neustart warten. (Layout-nahe
        # Optionen wie page_preview bleiben aussen vor - die braeuchten ein
        # Neuaufbauen der Oberflaeche.)
        self._render = bool(new_settings.get("browser_render", self._render))
        self._respect_robots = bool(new_settings.get("respect_robots", self._respect_robots))
        self._rate_limit_on = bool(new_settings.get("rate_limit_enabled", self._rate_limit_on))
        self._rate_per_minute = max(
            1, self._read_int(new_settings, "rate_per_minute", self._rate_per_minute)
        )

    @work(group="preview-reset")
    async def _reset_preview_service(self) -> None:
        """Schliesst den Vorschau-Browser, damit er mit neuen Einstellungen neu startet."""
        service, self._preview_service = self._preview_service, None
        if service is None:
            return
        with contextlib.suppress(Exception):
            self.workers.cancel_group(self, "page-preview")
        with contextlib.suppress(Exception):
            await service.close()

    def action_show_about(self) -> None:
        self.push_screen(
            AboutScreen(
                app_name="c2pa-scanner",
                version=__version__,
                author=__author__,
                release=__year__,
                description=t("about.description"),
                license="Apache-2.0",
                lang=current_language(),
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

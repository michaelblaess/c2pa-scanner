"""Textual-App: C2PA-/KI-Scanner mit Bildvorschau."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Header
from textual_fspicker import FileSave, SelectDirectory
from textual_themes import THEME_DISPLAY_NAMES, register_all
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
    VerticalSplitter,
)

from c2pa_scanner import __author__, __version__, __year__
from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.infrastructure.c2pa_reader import C2paLibReader
from c2pa_scanner.infrastructure.image_source import iter_images
from c2pa_scanner.infrastructure.settings import JsonSettingsStore
from c2pa_scanner.services.classify import classify
from c2pa_scanner.widgets.findings_table import FindingsTable
from c2pa_scanner.widgets.preview_panel import PreviewPanel

_ABOUT_DESCRIPTION = (
    "Selbstprüf-Werkzeug für C2PA-/KI-Herkunft in Bildern.\n\n"
    "Es prüft deine EIGENEN Bilder - ausdrücklich NICHT zum Durchleuchten fremder\n"
    "Seiten oder für Abmahnungen. Der C2PA-Scan ist nur ein Indiz, kein Rechtsgutachten.\n\n"
    "Rechtsgrundlage: EU AI Act (VO 2024/1689), Artikel 50 - gültig ab 2. August 2026."
)


class C2paScannerApp(CrashGuard, ClickableLinksMixin, LogRouter, App[None]):  # type: ignore[misc]
    """Hauptanwendung: Ordner scannen, C2PA/KI erkennen, Bild vorschauen."""

    CSS_PATH = "app.tcss"
    TITLE = f"c2pa-scanner v{__version__}"

    BINDINGS = [
        Binding("o,O", "choose_folder", "Ordner", key_display="o",
                tooltip="Einen Ordner zum Scannen auswaehlen"),
        Binding("c,C", "scan", "Scan", key_display="c",
                tooltip="Den aktuellen Ordner (erneut) auf C2PA/KI scannen"),
        Binding("m,M", "make_testimage", "Testbild", key_display="m",
                tooltip="Ein signiertes C2PA-Testbild erzeugen und speichern"),
        Binding("l,L", "toggle_log", "Log", key_display="l",
                tooltip="Log-Panel ein-/ausblenden"),
        Binding("t,T", "cycle_theme", "Theme", key_display="t",
                tooltip="Naechstes Retro-Theme"),
        Binding("s,S", "show_settings", "Settings", key_display="s",
                tooltip="Einstellungen oeffnen"),
        Binding("i,I", "show_about", "Info", key_display="i",
                tooltip="Ueber c2pa-scanner"),
        Binding("q,Q", "quit", "Beenden", key_display="q", tooltip="App beenden"),
    ]

    def __init__(self, start_folder: Path | None = None) -> None:
        super().__init__()
        self.crash_guard_lang = "de"
        register_all(self)

        self._settings_store = JsonSettingsStore()
        settings = self._settings_store.load()
        theme = settings.get("theme")
        if isinstance(theme, str) and theme in self.available_themes:
            self.theme = theme

        self._recursive = bool(settings.get("recursive", True))
        last = settings.get("last_folder")
        self._folder: Path | None = start_folder or (
            Path(str(last)) if isinstance(last, str) and last else None
        )
        self._reader = C2paLibReader()
        self._scanning = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield InfoHeader(
            [
                InfoItem("folder", "Ordner", "-"),
                InfoItem("total", "Bilder", "0"),
                InfoItem("label", "KI-Label noetig", "0"),
                InfoItem("errors", "Fehler", "0"),
            ],
            columns=4,
            separator="   |   ",
            id="stats",
        )
        with Horizontal(id="main"):
            yield FindingsTable(id="results")
            yield VerticalSplitter(target_id="results", min_size=30, id="vsplit")
            yield PreviewPanel(id="preview")
        yield HorizontalSplitter(target_id="main", min_size=8, id="logsplit", classes="hidden")
        yield LogPanel(lang="de", export_name="c2pa-scanner", id="log", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        self._update_stats()
        if self._folder is not None:
            self.action_scan()

    # --- Scan ---------------------------------------------------------------

    def action_scan(self) -> None:
        if self._folder is None:
            self.notify("Kein Ordner gewählt - mit 'o' einen auswählen.", severity="warning")
            return
        if self._scanning:
            return
        self._run_scan(self._folder)

    @work(thread=True, exclusive=True)
    def _run_scan(self, folder: Path) -> None:
        self._scanning = True
        self.call_from_thread(self._begin_scan)
        findings: list[ImageFinding] = []
        for path in iter_images(folder, recursive=self._recursive):
            try:
                has_c2pa, dst = self._reader.read(path)
                finding = ImageFinding(str(path), has_c2pa, dst, classify(dst, has_c2pa))
            except Exception as exc:  # noqa: BLE001 - defektes Bild darf den Lauf nicht killen
                finding = ImageFinding(str(path), False, None, Verdict.ERROR, str(exc))
            findings.append(finding)
            self.call_from_thread(self._add_row, finding)
        self.call_from_thread(self._finish_scan, findings)
        self._scanning = False

    def _begin_scan(self) -> None:
        table = self.query_one("#results", FindingsTable)
        table.scanning = True
        table.clear_findings()
        self.query_one("#preview", PreviewPanel).show_image(None)
        self.post_message(LogMessage.info(f"Scan: {self._folder}"))
        self._update_stats()

    def _add_row(self, finding: ImageFinding) -> None:
        self.query_one("#results", FindingsTable).add_finding(finding)
        self._update_stats()

    def _finish_scan(self, findings: list[ImageFinding]) -> None:
        table = self.query_one("#results", FindingsTable)
        table.scanning = False
        table.sort_now()
        needs = sum(1 for f in findings if f.verdict.needs_label)
        self.post_message(
            LogMessage.success(f"Fertig: {len(findings)} Bilder, {needs} Label-pflichtig")
        )
        self.notify(f"{len(findings)} Bilder gescannt, {needs} KI-Label nötig")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        finding = self.query_one("#results", FindingsTable).finding_for_key(event.row_key.value)
        if finding is not None:
            self.query_one("#preview", PreviewPanel).show_image(Path(finding.source))

    def _update_stats(self) -> None:
        header = self.query_one("#stats", InfoHeader)
        findings = self.query_one("#results", FindingsTable).findings
        total = len(findings)
        needs = sum(1 for f in findings if f.verdict.needs_label)
        errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
        header.set_value("folder", str(self._folder) if self._folder else "-")
        header.set_value("total", str(total))
        header.set_value("label", str(needs), value_style="bold red" if needs else "dim")
        header.set_value("errors", str(errors), value_style="bold red" if errors else "dim")

    # --- Ordnerwahl ---------------------------------------------------------

    def action_choose_folder(self) -> None:
        start = str(self._folder) if self._folder is not None else str(Path.cwd())
        self.push_screen(SelectDirectory(location=start), callback=self._on_folder_chosen)

    def _on_folder_chosen(self, path: Path | None) -> None:
        if path is None:
            return
        self._folder = Path(path)
        self._persist({"last_folder": str(self._folder)})
        self.action_scan()

    # --- Testbild -----------------------------------------------------------

    def action_make_testimage(self) -> None:
        location = str(self._folder) if self._folder is not None else str(Path.cwd())
        self.push_screen(
            FileSave(location=location, default_file="c2pa-testbild.jpg"),
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

    # --- Log / Theme / Settings / About ------------------------------------

    def action_toggle_log(self) -> None:
        self.query_one("#log", LogPanel).toggle_class("hidden")
        self.query_one("#logsplit", HorizontalSplitter).toggle_class("hidden")

    def action_cycle_theme(self) -> None:
        names = sorted(self.available_themes.keys())
        if not names:
            return
        try:
            idx = names.index(self.theme)
        except ValueError:
            idx = -1
        next_theme = names[(idx + 1) % len(names)]
        self.theme = next_theme
        self.notify(f"Theme: {THEME_DISPLAY_NAMES.get(next_theme, next_theme)}")

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
        self._recursive = bool(new_settings.get("recursive", self._recursive))

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

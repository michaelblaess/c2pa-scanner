"""Ergebnis-Tabelle: Suchleiste + Zaehler + sortierbare DataTable mit KI-Filter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Static
from textual_widgets import SearchInputWithHistory

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.i18n import t

_VERDICT_STYLE: dict[Verdict, tuple[str, str]] = {
    Verdict.AI_GENERATED: ("verdict.ai_generated", "bold red"),
    Verdict.AI_EDITED: ("verdict.ai_edited", "bold yellow"),
    Verdict.C2PA_OTHER: ("verdict.c2pa_other", "cyan"),
    Verdict.NO_C2PA: ("verdict.no_c2pa", "dim"),
    Verdict.ERROR: ("verdict.error", "bold red"),
}

_VERDICT_ORDER: dict[Verdict, int] = {
    Verdict.AI_GENERATED: 0,
    Verdict.AI_EDITED: 1,
    Verdict.C2PA_OTHER: 2,
    Verdict.NO_C2PA: 3,
    Verdict.ERROR: 4,
}


def _short_source_type(dst: str | None) -> str:
    if not dst:
        return "-"
    return dst.rstrip("/").rsplit("/", 1)[-1]


def _url_name(url: str) -> str:
    path = url.split("?")[0].split("#")[0].rstrip("/")
    return path.rsplit("/", 1)[-1] or url


def _page_path(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")


class ResultsDataTable(DataTable[str]):
    """DataTable, die einen Rechtsklick als RightClicked-Message meldet (Kontextmenue)."""

    class RightClicked(Message):
        def __init__(self, x: int, y: int) -> None:
            super().__init__()
            self.x = x
            self.y = y

    async def _on_click(self, event: events.Click) -> None:
        if event.button == 3:
            event.stop()
            meta = event.style.meta if event.style else {}
            row = meta.get("row", -1)
            # Auf einer Zeile: Cursor dorthin -> _current_finding aktuell. Im
            # leeren Bereich (row < 0) trotzdem das Menue oeffnen (Export/Toggle).
            if isinstance(row, int) and row >= 0:
                self.move_cursor(row=row)
            self.post_message(self.RightClicked(event.screen_x, event.screen_y))
            return
        await super()._on_click(event)


class FindingsTable(Vertical):
    """Container: Suchleiste, Trefferzaehler und die eigentliche DataTable."""

    filter_text: reactive[str] = reactive("")

    _SORT_KEYS: dict[int, Callable[[ImageFinding], Any]] = {
        0: lambda f: _VERDICT_ORDER[f.verdict],
        1: lambda f: (f.digital_source_type or f.generator or "").lower(),
        2: lambda f: _url_name(f.image_url).lower(),
        3: lambda f: f.width * f.height,
        4: lambda f: _page_path(f.page_url).lower(),
    }

    DEFAULT_CSS = """
    FindingsTable { height: 1fr; layout: vertical; }
    FindingsTable SearchInputWithHistory { height: 3; }
    FindingsTable #results-count { height: 1; color: $text-muted; padding: 0 1; }
    FindingsTable #results-data { height: 1fr; }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._findings: list[ImageFinding] = []
        self._filtered: list[ImageFinding] = []
        self._sort_col: int = 0
        self._sort_desc: bool = False
        self._base_labels: list[str] = []
        self._col_keys: list[Any] = []
        self.scanning: bool = False
        self._only_ai: bool = False

    @property
    def findings(self) -> list[ImageFinding]:
        return self._findings

    def shown_findings(self) -> list[ImageFinding]:
        """Die aktuell sichtbare (gefilterte) Teilmenge - fuer Export."""
        return self._filtered

    def compose(self) -> ComposeResult:
        yield SearchInputWithHistory(
            placeholder=t("table.filter_placeholder"),
            icon="🔍",
            input_id="filter-bar",
            dropdown_id="filter-dropdown",
        )
        yield Static("", id="results-count")
        yield ResultsDataTable(id="results-data", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#results-data", DataTable)
        self._base_labels = [
            t("table.status"),
            t("table.origin"),
            t("table.image"),
            t("table.size"),
            t("table.page"),
        ]
        self._col_keys = list(table.add_columns(*self._base_labels))
        self._update_sort_indicator()
        self._update_count()

    def watch_filter_text(self, value: str) -> None:
        if self.is_mounted:
            self._apply_filter()

    @on(Input.Changed, "#filter-bar")
    def _on_filter_changed(self, event: Input.Changed) -> None:
        self.filter_text = event.value

    # --- oeffentliche API --------------------------------------------------

    def clear_findings(self) -> None:
        self._findings = []
        self._filtered = []
        self.query_one("#results-data", DataTable).clear()
        self._update_count()

    def add_finding(self, finding: ImageFinding) -> None:
        self._findings.append(finding)
        if self._passes(finding):
            self._filtered.append(finding)
            self._append_row(finding, len(self._filtered) - 1)
        self._update_count()

    def finding_for_key(self, key: object) -> ImageFinding | None:
        if key is None:
            return None
        try:
            idx = int(str(key))
        except ValueError:
            return None
        return self._filtered[idx] if 0 <= idx < len(self._filtered) else None

    def sort_now(self) -> None:
        self._apply_filter()

    def set_only_ai(self, value: bool) -> None:
        self._only_ai = value
        self._apply_filter()

    def only_ai(self) -> bool:
        return self._only_ai

    # --- intern ------------------------------------------------------------

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        try:
            col_index = self._col_keys.index(event.column_key)
        except ValueError:
            return
        if col_index not in self._SORT_KEYS:
            return
        if self.scanning:
            self.app.notify(t("table.sort_disabled"), severity="warning")
            return
        if col_index == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col_index
            self._sort_desc = False
        self._apply_filter()

    def _passes(self, finding: ImageFinding) -> bool:
        if self._only_ai and not finding.verdict.needs_label:
            return False
        needle = self.filter_text.strip().lower()
        if not needle:
            return True
        label = t(_VERDICT_STYLE[finding.verdict][0]).lower()
        return (
            needle in finding.image_url.lower()
            or needle in finding.page_url.lower()
            or needle in label
            or needle in (finding.digital_source_type or finding.generator or "").lower()
        )

    def _append_row(self, finding: ImageFinding, idx: int) -> None:
        label_key, style = _VERDICT_STYLE[finding.verdict]
        label = t(label_key)
        if finding.verdict is Verdict.ERROR and finding.error:
            herkunft = finding.error
        elif finding.digital_source_type:
            herkunft = _short_source_type(finding.digital_source_type)
        elif finding.generator:
            herkunft = finding.generator
        elif finding.has_c2pa:
            herkunft = "C2PA"
        else:
            herkunft = "-"
        size = f"{finding.width}×{finding.height}" if finding.width and finding.height else "-"
        self.query_one("#results-data", DataTable).add_row(
            Text(label, style=style),
            herkunft,
            _url_name(finding.image_url),
            size,
            _page_path(finding.page_url),
            key=str(idx),
        )

    def _apply_filter(self) -> None:
        self._filtered = [f for f in self._findings if self._passes(f)]
        sort_key = self._SORT_KEYS[self._sort_col]
        self._filtered.sort(key=sort_key, reverse=self._sort_desc)
        table = self.query_one("#results-data", DataTable)
        table.clear()
        for idx, finding in enumerate(self._filtered):
            self._append_row(finding, idx)
        self._update_sort_indicator()
        self._update_count()

    def _update_count(self) -> None:
        total = len(self._findings)
        shown = len(self._filtered)
        text = (
            t("table.count_all", total=total)
            if shown == total
            else t("table.count_filtered", shown=shown, total=total)
        )
        self.query_one("#results-count", Static).update(text)

    def _update_sort_indicator(self) -> None:
        arrow = " ▼" if self._sort_desc else " ▲"
        table = self.query_one("#results-data", DataTable)
        for i, col_key in enumerate(self._col_keys):
            base = self._base_labels[i]
            label = f"{base}{arrow}" if i == self._sort_col else base
            column = table.columns.get(col_key)
            if column is not None:
                column.label = Text(label)
        table.refresh()

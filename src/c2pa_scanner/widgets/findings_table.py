"""Sortierbare DataTable fuer die Scan-Ergebnisse (Header-Klick + Pfeil-Indikator)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.text import Text
from textual.widgets import DataTable

from c2pa_scanner.domain.models import ImageFinding, Verdict

_VERDICT_STYLE: dict[Verdict, tuple[str, str]] = {
    Verdict.AI_GENERATED: ("KI-generiert", "bold red"),
    Verdict.AI_EDITED: ("KI-bearbeitet", "bold yellow"),
    Verdict.C2PA_OTHER: ("C2PA (kein KI)", "cyan"),
    Verdict.NO_C2PA: ("kein C2PA", "dim"),
    Verdict.ERROR: ("Fehler", "bold red"),
}

# Sortier-Reihenfolge der Verdicts (KI-relevantes zuerst).
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


class FindingsTable(DataTable[Any]):
    """DataTable, die ihre Findings selbst haelt und per Header-Klick sortiert."""

    # Nur Spalten in diesem dict sind klickbar/sortierbar.
    _SORT_KEYS: dict[int, Callable[[ImageFinding], Any]] = {
        0: lambda f: _VERDICT_ORDER[f.verdict],
        1: lambda f: (f.digital_source_type or "").lower(),
        2: lambda f: _url_name(f.image_url).lower(),
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self._findings: list[ImageFinding] = []
        self._sort_col: int = 0
        self._sort_desc: bool = False
        self._base_labels: list[str] = []
        self._col_keys: list[Any] = []
        self.scanning: bool = False

    @property
    def findings(self) -> list[ImageFinding]:
        return self._findings

    def on_mount(self) -> None:
        self._base_labels = ["Verdict", "digitalSourceType", "Bild"]
        self._col_keys = list(self.add_columns(*self._base_labels))
        self._update_sort_indicator()

    def clear_findings(self) -> None:
        self._findings = []
        self.clear()

    def add_finding(self, finding: ImageFinding) -> None:
        self._findings.append(finding)
        self._append_row(finding, len(self._findings) - 1)

    def finding_for_key(self, key: object) -> ImageFinding | None:
        if key is None:
            return None
        try:
            idx = int(str(key))
        except ValueError:
            return None
        if 0 <= idx < len(self._findings):
            return self._findings[idx]
        return None

    def sort_now(self) -> None:
        """Wendet die aktuelle Sortierung an (z.B. nach Scan-Ende)."""
        self._rebuild()
        self._update_sort_indicator()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        try:
            col_index = self._col_keys.index(event.column_key)
        except ValueError:
            return
        if col_index not in self._SORT_KEYS:
            return
        if self.scanning:
            self.app.notify("Sortierung waehrend des Scans deaktiviert.", severity="warning")
            return
        if col_index == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col_index
            self._sort_desc = False
        self.sort_now()

    def _append_row(self, finding: ImageFinding, idx: int) -> None:
        label, style = _VERDICT_STYLE[finding.verdict]
        self.add_row(
            Text(label, style=style),
            _short_source_type(finding.digital_source_type),
            _url_name(finding.image_url),
            key=str(idx),
        )

    def _rebuild(self) -> None:
        # Zeilen-Key bleibt der ORIGINAL-Index -> Vorschau-Zuordnung bleibt stabil.
        self.clear()
        sort_key = self._SORT_KEYS[self._sort_col]
        order = sorted(
            range(len(self._findings)),
            key=lambda i: sort_key(self._findings[i]),
            reverse=self._sort_desc,
        )
        for idx in order:
            self._append_row(self._findings[idx], idx)

    def _update_sort_indicator(self) -> None:
        arrow = " ▼" if self._sort_desc else " ▲"
        for i, col_key in enumerate(self._col_keys):
            base = self._base_labels[i]
            label = f"{base}{arrow}" if i == self._sort_col else base
            column = self.columns.get(col_key)
            if column is not None:
                column.label = Text(label)
        self.refresh()

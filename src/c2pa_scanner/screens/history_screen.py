"""History-Dialog: fruehere Sitemaps auswaehlen."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from c2pa_scanner.i18n import t
from c2pa_scanner.infrastructure.history import HistoryEntry


class HistoryScreen(ModalScreen[str | None]):
    """Listet gescannte Sitemaps; gibt die gewaehlte Sitemap-URL zurueck (oder None)."""

    DEFAULT_CSS = """
    HistoryScreen { align: center middle; }
    HistoryScreen > Vertical {
        width: 90%; max-width: 120; height: 80%; max-height: 30;
        background: $surface; border: thick $accent; padding: 1 2;
    }
    HistoryScreen #title { text-style: bold; color: $accent; height: 1; margin-bottom: 1; }
    HistoryScreen DataTable { height: 1fr; }
    HistoryScreen #buttons { height: 3; align: center middle; margin-top: 1; }
    HistoryScreen #buttons Button { margin: 0 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", t("common.close")),
        Binding("enter", "select", t("common.select")),
    ]

    def __init__(self, entries: list[HistoryEntry]) -> None:
        super().__init__()
        self._entries = entries

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(t("history.title"), id="title")
            yield DataTable(id="history-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(id="buttons"):
                yield Button(t("common.select"), variant="primary", id="hist-select")
                yield Button(t("common.close"), variant="default", id="hist-close")

    def on_mount(self) -> None:
        table: DataTable[str] = self.query_one("#history-table", DataTable)
        table.add_columns(
            t("history.col_sitemap"),
            t("history.col_when"),
            t("history.col_pages"),
            t("history.col_images"),
            t("history.col_ai"),
        )
        for i, entry in enumerate(self._entries):
            table.add_row(
                entry.sitemap,
                entry.at,
                str(entry.pages),
                str(entry.images),
                str(entry.needs_label),
                key=str(i),
            )
        if self._entries:
            table.focus()

    def _selected(self) -> str | None:
        table = self.query_one("#history-table", DataTable)
        if table.row_count == 0:
            return None
        cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        try:
            idx = int(str(cell_key.row_key.value))
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(self._entries):
            return self._entries[idx].sitemap
        return None

    def action_select(self) -> None:
        self.dismiss(self._selected())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(self._selected())

    @on(Button.Pressed, "#hist-select")
    def _on_select(self) -> None:
        self.dismiss(self._selected())

    @on(Button.Pressed, "#hist-close")
    def _on_close(self) -> None:
        self.dismiss(None)

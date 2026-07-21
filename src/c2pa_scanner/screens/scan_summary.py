"""Status-Screen nach einem Scan (analog console-error-scanner/sitemap-tracker)."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from c2pa_scanner.i18n import t


class ScanSummaryScreen(ModalScreen[None]):
    """Zeigt die Kennzahlen des letzten Scans."""

    DEFAULT_CSS = """
    ScanSummaryScreen { align: center middle; }
    ScanSummaryScreen > Vertical {
        width: auto; max-width: 100; height: auto; max-height: 90%;
        background: $surface; border: thick $accent; padding: 1 2;
    }
    ScanSummaryScreen #summary-title {
        text-style: bold; color: $accent; height: 1; margin-bottom: 1;
    }
    /* height: auto (NICHT 1fr) - sonst balloniert der Dialog auf max-height. */
    ScanSummaryScreen #summary-scroll { height: auto; max-height: 90%; }
    ScanSummaryScreen #summary-buttons { height: 3; align: center middle; margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "close", t("common.close")),
        Binding("enter", "close", t("common.close")),
    ]

    def __init__(
        self,
        *,
        sitemap: str,
        pages: int,
        images: int,
        c2pa: int,
        ai_label: int,
        errors: int,
        duration_s: float,
    ) -> None:
        super().__init__()
        self._sitemap = sitemap
        self._pages = pages
        self._images = images
        self._c2pa = c2pa
        self._ai_label = ai_label
        self._errors = errors
        self._duration_s = duration_s

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(t("summary.title"), id="summary-title")
            with VerticalScroll(id="summary-scroll"):
                yield Static(self._build())
            with Horizontal(id="summary-buttons"):
                button = Button(t("common.close"), variant="primary", id="sum-close")
                button.can_focus = False
                yield button

    def _row(self, text: Text, label: str, value: str, style: str = "") -> None:
        text.append(f"{label:<26}", style="bold")
        text.append(f"{value}\n", style=style)

    def _build(self) -> Text:
        text = Text()
        text.append(t("summary.sitemap"), style="bold")
        text.append(f"{self._sitemap}\n\n")
        self._row(text, t("summary.pages"), str(self._pages))
        self._row(text, t("summary.images"), str(self._images))
        self._row(
            text, t("summary.with_c2pa"), str(self._c2pa),
            "bold cyan" if self._c2pa else "dim",
        )
        self._row(
            text, t("summary.ai_label"), str(self._ai_label),
            "bold red" if self._ai_label else "dim",
        )
        self._row(
            text, t("summary.errors"), str(self._errors), "bold red" if self._errors else "dim"
        )
        self._row(text, t("summary.duration"), f"{self._duration_s:.1f} s")
        return text

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#sum-close")
    def _on_close(self) -> None:
        self.dismiss(None)

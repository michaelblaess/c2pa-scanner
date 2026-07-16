"""Status-Screen nach einem Scan (analog console-error-scanner/sitemap-tracker)."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ScanSummaryScreen(ModalScreen[None]):
    """Zeigt die Kennzahlen des letzten Scans."""

    DEFAULT_CSS = """
    ScanSummaryScreen { align: center middle; }
    ScanSummaryScreen > Vertical {
        width: 80%; max-width: 90; height: auto; max-height: 90%;
        background: $surface; border: thick $accent; padding: 1 2;
    }
    ScanSummaryScreen #summary-title {
        text-style: bold; color: $accent; height: 1; margin-bottom: 1;
    }
    ScanSummaryScreen #summary-buttons { height: 3; align: center middle; margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "close", "Schließen"),
        Binding("enter", "close", "Schließen"),
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
            yield Static("Scan abgeschlossen", id="summary-title")
            with VerticalScroll():
                yield Static(self._build())
            with Horizontal(id="summary-buttons"):
                button = Button("Schließen", variant="primary", id="sum-close")
                button.can_focus = False
                yield button

    def _row(self, text: Text, label: str, value: str, style: str = "") -> None:
        text.append(f"{label:<26}", style="bold")
        text.append(f"{value}\n", style=style)

    def _build(self) -> Text:
        text = Text()
        text.append("Sitemap: ", style="bold")
        text.append(f"{self._sitemap}\n\n")
        self._row(text, "Seiten gecrawlt", str(self._pages))
        self._row(text, "Bilder geprüft", str(self._images))
        self._row(
            text, "davon mit C2PA-Manifest", str(self._c2pa),
            "bold cyan" if self._c2pa else "dim",
        )
        self._row(
            text, "davon KI (Label nötig)", str(self._ai_label),
            "bold red" if self._ai_label else "dim",
        )
        self._row(text, "Fehler", str(self._errors), "bold red" if self._errors else "dim")
        self._row(text, "Dauer", f"{self._duration_s:.1f} s")
        return text

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#sum-close")
    def _on_close(self) -> None:
        self.dismiss(None)

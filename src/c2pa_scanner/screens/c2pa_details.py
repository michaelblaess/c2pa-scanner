"""Modal: rohes C2PA-Manifest eines Bildes anzeigen."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from c2pa_scanner.i18n import t


class C2paDetailsScreen(ModalScreen[None]):
    """Zeigt das C2PA-Manifest (JSON) des markierten Bildes."""

    DEFAULT_CSS = """
    C2paDetailsScreen { align: center middle; }
    C2paDetailsScreen > Vertical {
        width: 90%; max-width: 120; height: auto; max-height: 90%;
        background: $surface; border: thick $accent; padding: 1 2;
    }
    C2paDetailsScreen #c2pa-title { text-style: bold; color: $accent; height: 1; margin-bottom: 1; }
    C2paDetailsScreen #c2pa-scroll { height: auto; max-height: 90%; }
    C2paDetailsScreen #c2pa-buttons { height: 3; align: center middle; margin-top: 1; }
    C2paDetailsScreen #c2pa-buttons Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "close", t("common.close"))]

    def __init__(self, title: str, manifest_json: str | None) -> None:
        super().__init__()
        self._title = title
        self._json = manifest_json

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(t("details.title", name=self._title), id="c2pa-title")
            with VerticalScroll(id="c2pa-scroll"):
                yield Static(
                    self._json or t("details.empty"),
                    id="c2pa-json",
                    markup=False,
                )
            with Horizontal(id="c2pa-buttons"):
                yield Button(t("common.copy"), id="c2pa-copy")
                yield Button(t("common.close"), variant="primary", id="c2pa-close")

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#c2pa-copy")
    def _on_copy(self) -> None:
        if self._json:
            self.app.copy_to_clipboard(self._json)
            self.app.notify(t("notify.manifest_copied"))

    @on(Button.Pressed, "#c2pa-close")
    def _on_close(self) -> None:
        self.dismiss(None)

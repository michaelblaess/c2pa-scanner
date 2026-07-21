"""Modal 'Proxy / Gateway erkannt' - erklaert, warum der Scan leer bleibt."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from c2pa_scanner.i18n import t
from c2pa_scanner.infrastructure.proxy_detect import ProxyDetection


class ProxyWarningScreen(ModalScreen[None]):
    """Warnt, dass ein Proxy-/Auth-Gateway die Seiten-Abrufe abfaengt."""

    DEFAULT_CSS = """
    ProxyWarningScreen { align: center middle; }
    ProxyWarningScreen > Vertical {
        width: 80%; max-width: 90; height: auto; max-height: 90%;
        background: $surface; border: thick $warning; padding: 1 2;
    }
    ProxyWarningScreen #title { text-style: bold; color: $warning; height: 1; margin-bottom: 1; }
    ProxyWarningScreen #buttons { height: 3; align: center middle; margin-top: 1; }
    """

    BINDINGS = [Binding("escape", "close", t("common.close"))]

    def __init__(self, detection: ProxyDetection) -> None:
        super().__init__()
        self._detection = detection

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(t("proxy.title"), id="title")
            with VerticalScroll():
                yield Static(t("proxy.body", host=self._detection.host))
            with Horizontal(id="buttons"):
                button = Button(t("common.close"), variant="primary", id="proxy-close")
                button.can_focus = False
                yield button

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#proxy-close")
    def _on_close(self) -> None:
        self.dismiss(None)

"""Modal 'Proxy / Gateway erkannt' - erklaert, warum der Scan leer bleibt."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

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

    BINDINGS = [Binding("escape", "close", "Schließen")]

    def __init__(self, detection: ProxyDetection) -> None:
        super().__init__()
        self._detection = detection

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Proxy / Gateway erkannt", id="title")
            with VerticalScroll():
                yield Static(
                    "Die Anfragen werden von einem vorgeschalteten Proxy- oder Auth-Gateway "
                    "abgefangen und auf einen fremden Host umgeleitet:\n\n"
                    f"  {self._detection.host}\n\n"
                    "Dadurch werden keine echten Seiten und Bilder erreicht - der Scan bleibt "
                    "leer.\n\n"
                    "Trage in den Einstellungen (s) die Proxy-URL Deines Zscaler-/Corporate-"
                    "Proxys ein (z.B. http://proxy-host:port) und starte den Scan erneut."
                )
            with Horizontal(id="buttons"):
                button = Button("Schließen", variant="primary", id="proxy-close")
                button.can_focus = False
                yield button

    def action_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#proxy-close")
    def _on_close(self) -> None:
        self.dismiss(None)

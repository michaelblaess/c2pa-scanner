"""Splitter mit voll sichtbarem Grip - der Handle geht ueber die ganze Laenge.

Die textual-widgets-Splitter rendern nur einen 4-Zeichen-Handle in der Mitte.
Diese Subklassen zeichnen den Handle durchgehend, damit der Splitter als
sichtbare Griff-Linie erkennbar ist. Das Drag-Verhalten bleibt unveraendert.
"""

from __future__ import annotations

from textual.app import RenderResult
from textual_widgets import HorizontalSplitter, VerticalSplitter

_VERTICAL_HANDLE = "┊"
_HORIZONTAL_HANDLE = "┄"


class GripVerticalSplitter(VerticalSplitter):  # type: ignore[misc]
    """Vertikaler Splitter mit durchgehendem Grip."""

    def render(self) -> RenderResult:
        height = max(1, self.size.height)
        return "\n".join(_VERTICAL_HANDLE for _ in range(height))


class GripHorizontalSplitter(HorizontalSplitter):  # type: ignore[misc]
    """Horizontaler Splitter mit durchgehendem Grip."""

    def render(self) -> RenderResult:
        width = max(1, int(self.size.width))
        return _HORIZONTAL_HANDLE * width

"""Bildvorschau-Panel: textual-image (TGP/Sixel) mit Halfblock-Fallback."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
from typing import Any, cast

from PIL import Image as PILImage
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

_UPPER_HALF_BLOCK = "▀"


def select_graphics_backend() -> str | None:
    """Heuristik: 'tgp', 'sixel' oder None (Halfblock-Fallback)."""
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term or "ghostty" in term:
        return "tgp"
    if term_program in ("wezterm", "ghostty") or os.environ.get("KONSOLE_VERSION"):
        return "tgp"
    if os.environ.get("WT_SESSION"):
        return "sixel"
    if term in ("foot", "xterm", "mlterm", "mintty") or term_program in ("mintty", "iterm.app"):
        return "sixel"
    return None


def _load_graphics_widget_class(backend: str | None) -> type[Widget] | None:
    if backend is None:
        return None
    try:
        if backend == "tgp":
            from textual_image.widget import TGPImage

            return TGPImage
        from textual_image.widget import SixelImage

        return SixelImage
    except ImportError:
        return None


def _render_half_blocks(data: bytes, max_width: int, max_height: int) -> Text:
    """Rendert ein Bild als Unicode-Half-Blocks (2 Pixel pro Zeichen)."""
    img = PILImage.open(io.BytesIO(data)).convert("RGB")
    orig_w, orig_h = img.size
    pixel_h = max_height * 2
    scale = min(max_width / orig_w, pixel_h / orig_h)
    new_w = max(1, int(orig_w * scale))
    new_h = max(2, int(orig_h * scale))
    if new_h % 2:
        new_h += 1
    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

    out = Text()
    for y in range(0, new_h, 2):
        for x in range(new_w):
            top = cast("tuple[int, int, int]", img.getpixel((x, y)))
            bot = cast("tuple[int, int, int]", img.getpixel((x, y + 1)))
            out.append(
                _UPPER_HALF_BLOCK,
                style=f"rgb({top[0]},{top[1]},{top[2]}) on rgb({bot[0]},{bot[1]},{bot[2]})",
            )
        out.append("\n")
    return out


class PreviewPanel(Widget):
    """Zeigt eine Bildvorschau des in der Tabelle markierten Bildes."""

    DEFAULT_CSS = """
    PreviewPanel { height: 1fr; padding: 0 1; }
    PreviewPanel #preview-title { height: 1; text-style: bold; color: $accent; }
    PreviewPanel .graphics-image { width: auto; height: auto; }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._backend = select_graphics_backend()
        self._widget_cls = _load_graphics_widget_class(self._backend)

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Keine Auswahl", id="preview-title")
            if self._widget_cls is not None:
                yield self._widget_cls(id="preview-image", classes="graphics-image")
            else:
                yield Static("", id="preview-image")

    def show_image(self, path: Path | None) -> None:
        title = self.query_one("#preview-title", Static)
        title.update(path.name if path is not None else "Keine Auswahl")
        if path is None:
            self._clear()
            return
        try:
            data = path.read_bytes()
        except OSError:
            self._clear()
            return
        if self._widget_cls is not None:
            from textual_image.widget._base import Image as BaseImage

            with contextlib.suppress(Exception):
                img = PILImage.open(io.BytesIO(data)).convert("RGB")
                self.query_one("#preview-image", BaseImage).image = img
        else:
            with contextlib.suppress(Exception):
                self.query_one("#preview-image", Static).update(
                    _render_half_blocks(data, 60, 30)
                )

    def _clear(self) -> None:
        if self._widget_cls is not None:
            from textual_image.widget._base import Image as BaseImage

            with contextlib.suppress(Exception):
                self.query_one("#preview-image", BaseImage).image = None
        else:
            with contextlib.suppress(Exception):
                self.query_one("#preview-image", Static).update("")

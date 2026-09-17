"""Seiten laden und die Bild-URLs extrahieren.

Wichtig: Viele CMS (z.B. Sitefinity mit Web-Components wie <envc-hero-section>)
tragen die Bild-URL NICHT in <img src>, sondern in Custom-Element-Attributen
(image-src, background, ...) oder bauen das <img> erst per JS im Shadow-DOM. Die
URL steht aber im Server-HTML. Deshalb wird zusaetzlich zum <img>-Parser das
gesamte HTML per Regex nach Bild-URLs durchsucht - das faengt diese Faelle ab,
ohne einen echten Browser (Playwright) zu brauchen.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

import httpx

_IMG_EXT = r"(?:jpe?g|png|webp|avif|heic|heif|gif|tiff?|bmp)"
# Absolute (https://...) oder wurzel-relative (/...) URL, die auf eine Bildendung
# zeigt, optional mit Querystring. HTML-Entities (&amp;) werden danach dekodiert.
_IMG_URL_RE = re.compile(
    r"""(?:https?://[^\s"'<>()]+|/[^\s"'<>()]+)\.""" + _IMG_EXT + r"""(?:[?&][^\s"'<>()]*)?""",
    re.IGNORECASE,
)


class _ImgParser(HTMLParser):
    """Sammelt src/data-src/srcset aus allen <img>-Tags und die Stellen fuer die Regex-Suche.

    Die Regex-Suche laeuft nur ueber Markup: Attributwerte aller Tags sowie den
    Inhalt von <script> und <style>. Text zwischen den Tags bleibt aussen vor -
    sonst wird ein Dateiname im Fliesstext oder in einem Codeblock
    (`make-testimage ./test-ai.jpg`) zur Bild-URL und endet als HTTP 404.
    """

    _RAW_TEXT_TAGS = ("script", "style")

    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []
        self.markup: list[str] = []
        self._raw_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Attributwerte kommen bereits entity-dekodiert an (&quot; -> ")
        self.markup.extend(value for _, value in attrs if value)
        if tag.lower() in self._RAW_TEXT_TAGS:
            self._raw_text_depth += 1
        if tag.lower() != "img":
            return
        values = {name.lower(): (value or "") for name, value in attrs}
        candidate = values.get("src") or values.get("data-src")
        if candidate:
            self.srcs.append(candidate)
        srcset = values.get("srcset")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            if first:
                self.srcs.append(first)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in self._RAW_TEXT_TAGS:
            self._raw_text_depth -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._RAW_TEXT_TAGS and self._raw_text_depth > 0:
            self._raw_text_depth -= 1

    def handle_data(self, data: str) -> None:
        # Inhalt von <script>/<style> liefert der Parser roh, deshalb hier dekodieren
        if self._raw_text_depth > 0:
            self.markup.append(unescape(data))


def _is_svg(url: str) -> bool:
    """True, wenn die URL auf eine SVG-Datei zeigt (SVG kann kein C2PA tragen)."""
    return url.split("?")[0].split("#")[0].lower().rstrip("/").endswith(".svg")


def extract_image_urls_from_html(html: str, base_url: str) -> list[str]:
    """Loest alle Bild-Quellen relativ zu base_url auf (absolut, dedupliziert).

    Findet <img>-Quellen UND alle Bild-URLs, die sonst im HTML stehen (Attribute
    von Web-Components, JSON, CSS). SVGs werden uebersprungen.
    """
    seen: set[str] = set()
    result: list[str] = []

    def add(raw: str) -> None:
        if not raw or raw.startswith("data:"):
            return
        absolute = urldefrag(urljoin(base_url, unescape(raw.strip())))[0]
        if absolute and absolute not in seen and not _is_svg(absolute):
            seen.add(absolute)
            result.append(absolute)

    parser = _ImgParser()
    parser.feed(html)
    for src in parser.srcs:
        add(src)
    # Jedes Fragment einzeln durchsuchen, damit die Zeichenklasse nicht ueber
    # Attributgrenzen hinweglaeuft. Entities muessen dabei aufgeloest sein: in
    # eingebettetem JSON stehen die String-Grenzen als &quot;, roh wuerde die Regex
    # JSON-Fragmente (z.B. /RestApi/comments-api/... bis zum naechsten Bildsuffix)
    # als eine Muell-URL einfangen. Das erledigt der Parser (siehe _ImgParser).
    for fragment in parser.markup:
        for match in _IMG_URL_RE.finditer(fragment):
            add(match.group(0))

    return result


async def fetch_page_images(client: httpx.AsyncClient, page_url: str) -> list[str]:
    """Laedt eine Seite und gibt ihre absoluten Bild-URLs zurueck."""
    response = await client.get(page_url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        return []
    return extract_image_urls_from_html(response.text, str(response.url))

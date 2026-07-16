"""Seiten laden und die Bild-URLs (<img>) extrahieren."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

import httpx


class _ImgParser(HTMLParser):
    """Sammelt src/data-src/srcset aus allen <img>-Tags."""

    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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


def extract_image_urls_from_html(html: str, base_url: str) -> list[str]:
    """Loest alle <img>-Quellen relativ zu base_url auf (absolut, dedupliziert)."""
    parser = _ImgParser()
    parser.feed(html)
    seen: set[str] = set()
    result: list[str] = []
    for src in parser.srcs:
        if src.startswith("data:"):
            continue
        absolute = urldefrag(urljoin(base_url, src))[0]
        if absolute and absolute not in seen:
            seen.add(absolute)
            result.append(absolute)
    return result


async def fetch_page_images(client: httpx.AsyncClient, page_url: str) -> list[str]:
    """Laedt eine Seite und gibt ihre absoluten Bild-URLs zurueck."""
    response = await client.get(page_url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        return []
    return extract_image_urls_from_html(response.text, str(response.url))

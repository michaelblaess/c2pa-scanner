"""Sitemap laden (URL oder lokale Datei), inkl. verschachtelter Sitemap-Indexe."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import httpx


def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


async def _fetch_text(client: httpx.AsyncClient, source: str) -> str:
    if _is_url(source):
        response = await client.get(source)
        response.raise_for_status()
        return response.text
    return Path(source).read_text(encoding="utf-8")


def parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """Zerlegt eine Sitemap in (Seiten-URLs, verschachtelte Sitemap-URLs)."""
    root = ET.fromstring(xml_text)
    pages: list[str] = []
    nested: list[str] = []
    for entry in root:
        loc: str | None = None
        for child in entry:
            if _localname(child.tag) == "loc" and child.text:
                loc = child.text.strip()
                break
        if not loc:
            continue
        if _localname(entry.tag) == "sitemap":
            nested.append(loc)
        else:
            pages.append(loc)
    return pages, nested


async def load_sitemap(
    client: httpx.AsyncClient, source: str, max_nested: int = 50
) -> list[str]:
    """Laedt eine Sitemap und liefert die deduplizierten Seiten-URLs.

    Ein Sitemap-Index wird eine Ebene tief aufgeloest (bis max_nested Kinder).
    """
    text = await _fetch_text(client, source)
    pages, nested = parse_sitemap(text)
    result = list(pages)
    for sitemap_url in nested[:max_nested]:
        try:
            sub_text = await _fetch_text(client, sitemap_url)
            sub_pages, _ = parse_sitemap(sub_text)
            result.extend(sub_pages)
        except Exception:  # noqa: BLE001 - eine kaputte Unter-Sitemap darf nicht alles killen
            continue

    seen: set[str] = set()
    unique: list[str] = []
    for url in result:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique

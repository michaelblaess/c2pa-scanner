"""Sitemap laden (URL oder lokale Datei), inkl. verschachtelter Sitemap-Indexe.

Wird eine Website-URL statt einer Sitemap-XML angegeben (z.B. die Startseite),
wird die echte Sitemap automatisch gesucht - Strategie wie im console-error-
scanner: zuerst die ``Sitemap:``-Zeilen der robots.txt, danach die gaengigen
Standardpfade. Der erste Kandidat, der gueltiges Sitemap-XML liefert, gewinnt.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

# Typische Sitemap-Pfade fuer die Auto-Discovery (in Prioritaetsreihenfolge).
_COMMON_SITEMAP_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap/sitemap.xml",
    "/sitemapindex.xml",
    "/sitemap/index.xml",
)


def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def is_sitemap_url(url: str) -> bool:
    """Prueft, ob eine URL direkt auf eine Sitemap zeigt (Pfad endet auf .xml)."""
    return urlsplit(url).path.lower().endswith(".xml")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


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


def _parse_robots_sitemaps(robots_text: str) -> list[str]:
    """Extrahiert die Sitemap-URLs aus den ``Sitemap:``-Zeilen der robots.txt."""
    urls: list[str] = []
    for line in robots_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            url = stripped[len("sitemap:") :].strip()
            if url:
                urls.append(url)
    return urls


async def _is_valid_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    """Prueft, ob eine URL echtes Sitemap-XML liefert (nicht z.B. eine HTML-404)."""
    try:
        response = await client.get(url)
    except Exception:  # noqa: BLE001 - unerreichbarer Kandidat gilt als ungueltig
        return False
    if response.status_code != 200:
        return False
    head = response.text[:1024].lower()
    return "<urlset" in head or "<sitemapindex" in head


async def discover_sitemap(
    client: httpx.AsyncClient, base_url: str, on_log: Callable[[str], None] | None
) -> str:
    """Findet die Sitemap-URL fuer eine Website automatisch.

    Zuerst die robots.txt (``Sitemap:``-Zeilen), danach die Standardpfade. Gibt
    die erste URL zurueck, die gueltiges Sitemap-XML liefert.

    Raises:
        ValueError:
            Wenn keine Sitemap gefunden wird.
    """

    def log(message: str) -> None:
        if on_log is not None:
            on_log(message)

    origin = _origin(base_url)
    log(f"Keine direkte Sitemap - suche automatisch für {origin} ...")

    # Phase 1: robots.txt nach Sitemap-Eintraegen durchsuchen.
    try:
        response = await client.get(f"{origin}/robots.txt")
        if response.status_code == 200:
            for candidate in _parse_robots_sitemaps(response.text):
                if await _is_valid_sitemap(client, candidate):
                    log(f"Sitemap gefunden (robots.txt): {candidate}")
                    return candidate
    except Exception:  # noqa: BLE001 - robots.txt ist optional
        pass

    # Phase 2: typische Pfade durchprobieren.
    for path in _COMMON_SITEMAP_PATHS:
        candidate = f"{origin}{path}"
        if await _is_valid_sitemap(client, candidate):
            log(f"Sitemap gefunden (Standardpfad): {candidate}")
            return candidate

    raise ValueError(
        f"Keine Sitemap gefunden für {base_url} - bitte eine direkte "
        f"Sitemap-URL angeben (z.B. {origin}/sitemap.xml)."
    )


async def load_sitemap(
    client: httpx.AsyncClient,
    source: str,
    max_nested: int = 50,
    on_log: Callable[[str], None] | None = None,
) -> list[str]:
    """Laedt eine Sitemap und liefert die deduplizierten Seiten-URLs.

    Ist ``source`` eine Website-URL ohne ``.xml`` (z.B. die Startseite), wird die
    echte Sitemap zuerst automatisch gesucht. Ein Sitemap-Index wird eine Ebene
    tief aufgeloest (bis max_nested Kinder).
    """
    if _is_url(source) and not is_sitemap_url(source):
        source = await discover_sitemap(client, source, on_log)

    try:
        text = await _fetch_text(client, source)
        pages, nested = parse_sitemap(text)
    except ET.ParseError:
        # Eine .xml-URL, die doch kein Sitemap-XML ist -> noch die Discovery versuchen.
        if not _is_url(source):
            raise
        source = await discover_sitemap(client, source, on_log)
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

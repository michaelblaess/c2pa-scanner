"""SitemapScanService: Sitemap -> Seiten -> Bilder -> C2PA (async, mit Callbacks)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.infrastructure.c2pa_reader import image_size, read_bytes
from c2pa_scanner.infrastructure.sitemap import load_sitemap
from c2pa_scanner.infrastructure.web import fetch_page_images
from c2pa_scanner.services.classify import classify

_USER_AGENT = "Mozilla/5.0 (c2pa-scanner)"

# Fortschritt: (phase, erledigt, gesamt) - phase ist "pages" oder "images".
ProgressCallback = Callable[[str, int, int], None]


def _failure_reason(exc: Exception) -> str:
    """Kurzer, lesbarer Grund fuer einen fehlgeschlagenen Abruf (HTTP-Code o.ae.)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "Timeout"
    if isinstance(exc, httpx.ConnectError):
        return "Verbindung fehlgeschlagen"
    if isinstance(exc, httpx.ProxyError):
        return "Proxy-Fehler"
    return type(exc).__name__


def _probe(data: bytes, content_type: str) -> tuple[bool, str | None, int, int]:
    """Laeuft im Thread: liest C2PA-Manifest UND Bildgroesse aus den Bytes."""
    has_c2pa, dst = read_bytes(data, content_type)
    width, height = image_size(data)
    return has_c2pa, dst, width, height


class SitemapScanService:
    """Crawlt die Seiten einer Sitemap und prueft ihre Bilder auf C2PA/KI."""

    def __init__(
        self, page_concurrency: int = 8, image_concurrency: int = 8, timeout: float = 30.0
    ) -> None:
        self._page_concurrency = page_concurrency
        self._image_concurrency = image_concurrency
        self._timeout = timeout
        self._min_size = 0

    async def scan(
        self,
        source: str,
        *,
        on_pages: Callable[[int], None],
        on_finding: Callable[[ImageFinding], None],
        on_log: Callable[[str], None],
        on_progress: ProgressCallback | None = None,
        proxy: str = "",
        min_image_size: int = 0,
    ) -> None:
        self._min_size = min_image_size
        headers = {"User-Agent": _USER_AGENT}
        async with httpx.AsyncClient(
            verify=False,
            follow_redirects=True,
            timeout=self._timeout,
            headers=headers,
            proxy=proxy.strip() or None,
        ) as client:
            on_log(f"Lade Sitemap: {source}")
            pages = await load_sitemap(client, source)
            on_pages(len(pages))
            on_log(f"{len(pages)} Seiten in der Sitemap")

            # Pipeline: sobald eine Seite ihre Bilder liefert, werden sie SOFORT
            # geprueft (kein Sammel-Barrier vor der Bildpruefung) -> die Tabelle
            # streamt live, waehrend noch gecrawlt wird.
            page_sem = asyncio.Semaphore(self._page_concurrency)
            image_sem = asyncio.Semaphore(self._image_concurrency)
            seen: set[str] = set()
            seen_lock = asyncio.Lock()
            image_tasks: list[asyncio.Task[None]] = []
            pages_done = 0
            skipped = 0
            total_pages = len(pages)

            async def check_image(image_url: str, page_url: str) -> None:
                nonlocal skipped
                async with image_sem:
                    finding = await self._check_image(client, image_url, page_url)
                if finding is None:  # zu klein -> uebersprungen
                    skipped += 1
                    return
                on_finding(finding)
                if finding.verdict is Verdict.ERROR and finding.error:
                    on_log(f"Bild fehlgeschlagen ({finding.error}): {image_url}")

            async def scan_page(page_url: str) -> None:
                nonlocal pages_done
                async with page_sem:
                    try:
                        images = await fetch_page_images(client, page_url)
                    except Exception as exc:  # noqa: BLE001 - kaputte Seite darf den Lauf nicht killen
                        on_log(f"Seite fehlgeschlagen ({_failure_reason(exc)}): {page_url}")
                        images = []
                    for image_url in images:
                        async with seen_lock:
                            if image_url in seen:
                                continue
                            seen.add(image_url)
                        image_tasks.append(
                            asyncio.create_task(check_image(image_url, page_url))
                        )
                pages_done += 1
                if on_progress is not None:
                    on_progress("pages", pages_done, total_pages)

            await asyncio.gather(*(scan_page(page_url) for page_url in pages))
            on_log(f"{len(seen)} eindeutige Bilder gefunden")
            if image_tasks:
                await asyncio.gather(*image_tasks)
            if skipped:
                on_log(f"{skipped} Bilder uebersprungen (schmaler als {self._min_size}px)")

    async def _check_image(
        self, client: httpx.AsyncClient, image_url: str, page_url: str
    ) -> ImageFinding | None:
        try:
            response = await client.get(image_url)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("content-type", "")
        except Exception as exc:  # noqa: BLE001 - Netzwerkfehler als Finding melden
            return ImageFinding(
                image_url, page_url, False, None, Verdict.ERROR, _failure_reason(exc)
            )
        has_c2pa, dst, width, height = await asyncio.to_thread(_probe, data, content_type)
        if self._min_size > 0 and 0 < width < self._min_size:
            return None
        return ImageFinding(
            image_url, page_url, has_c2pa, dst, classify(dst, has_c2pa),
            width=width, height=height,
        )

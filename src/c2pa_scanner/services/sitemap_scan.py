"""SitemapScanService: Sitemap -> Seiten -> Bilder -> C2PA (async, mit Callbacks)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.infrastructure.c2pa_reader import read_bytes
from c2pa_scanner.infrastructure.sitemap import load_sitemap
from c2pa_scanner.infrastructure.web import fetch_page_images
from c2pa_scanner.services.classify import classify

_USER_AGENT = "Mozilla/5.0 (c2pa-scanner)"


class SitemapScanService:
    """Crawlt die Seiten einer Sitemap und prueft ihre Bilder auf C2PA/KI."""

    def __init__(
        self, page_concurrency: int = 8, image_concurrency: int = 8, timeout: float = 30.0
    ) -> None:
        self._page_concurrency = page_concurrency
        self._image_concurrency = image_concurrency
        self._timeout = timeout

    async def scan(
        self,
        source: str,
        *,
        on_pages: Callable[[int], None],
        on_finding: Callable[[ImageFinding], None],
        on_log: Callable[[str], None],
    ) -> None:
        headers = {"User-Agent": _USER_AGENT}
        async with httpx.AsyncClient(
            verify=False, follow_redirects=True, timeout=self._timeout, headers=headers
        ) as client:
            on_log(f"Lade Sitemap: {source}")
            pages = await load_sitemap(client, source)
            on_pages(len(pages))
            on_log(f"{len(pages)} Seiten in der Sitemap")

            image_to_page = await self._collect_images(client, pages, on_log)
            on_log(f"{len(image_to_page)} eindeutige Bilder gefunden")

            image_sem = asyncio.Semaphore(self._image_concurrency)

            async def check(image_url: str, page_url: str) -> None:
                async with image_sem:
                    on_finding(await self._check_image(client, image_url, page_url))

            await asyncio.gather(
                *(check(image_url, page_url) for image_url, page_url in image_to_page.items())
            )

    async def _collect_images(
        self, client: httpx.AsyncClient, pages: list[str], on_log: Callable[[str], None]
    ) -> dict[str, str]:
        page_sem = asyncio.Semaphore(self._page_concurrency)
        image_to_page: dict[str, str] = {}
        lock = asyncio.Lock()

        async def scan_page(page_url: str) -> None:
            async with page_sem:
                try:
                    images = await fetch_page_images(client, page_url)
                except Exception:  # noqa: BLE001 - eine kaputte Seite darf den Lauf nicht killen
                    on_log(f"Seite fehlgeschlagen: {page_url}")
                    return
                async with lock:
                    for image_url in images:
                        image_to_page.setdefault(image_url, page_url)

        await asyncio.gather(*(scan_page(page_url) for page_url in pages))
        return image_to_page

    async def _check_image(
        self, client: httpx.AsyncClient, image_url: str, page_url: str
    ) -> ImageFinding:
        try:
            response = await client.get(image_url)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("content-type", "")
        except Exception as exc:  # noqa: BLE001 - Netzwerkfehler als Finding melden
            return ImageFinding(image_url, page_url, False, None, Verdict.ERROR, str(exc))
        has_c2pa, dst = await asyncio.to_thread(read_bytes, data, content_type)
        return ImageFinding(image_url, page_url, has_c2pa, dst, classify(dst, has_c2pa))

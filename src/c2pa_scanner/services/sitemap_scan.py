"""SitemapScanService: Sitemap -> Seiten -> Bilder -> C2PA (async, mit Callbacks)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack

import httpx

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.i18n import t
from c2pa_scanner.infrastructure.browser import PageRenderer
from c2pa_scanner.infrastructure.c2pa_reader import image_size, read_provenance
from c2pa_scanner.infrastructure.rate_limit import RateLimiter
from c2pa_scanner.infrastructure.robots import RobotsChecker
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
        return t("error.timeout")
    if isinstance(exc, httpx.ConnectError):
        return t("error.connect")
    if isinstance(exc, httpx.ProxyError):
        return t("error.proxy")
    return type(exc).__name__


def _probe(data: bytes, content_type: str) -> tuple[bool, str | None, str | None, int, int]:
    """Laeuft im Thread: liest C2PA/XMP/EXIF-Herkunft UND Bildgroesse aus den Bytes."""
    has_c2pa, dst, generator = read_provenance(data, content_type)
    width, height = image_size(data)
    return has_c2pa, dst, generator, width, height


class SitemapScanService:
    """Crawlt die Seiten einer Sitemap und prueft ihre Bilder auf C2PA/KI."""

    def __init__(
        self,
        page_concurrency: int = 8,
        image_concurrency: int = 8,
        timeout: float = 30.0,
        rate_per_minute: int = 60,
    ) -> None:
        self._page_concurrency = page_concurrency
        self._image_concurrency = image_concurrency
        self._timeout = timeout
        self._min_size = 0
        # 0 = kein Limit. Der Limiter zaehlt ALLE Requests (Seiten, Render-Aufrufe
        # und Bilder), weil Bilder haeufig auf derselben Maschine liegen wie die
        # Seiten - ein reines Seiten-Limit wuerde die halbe Last durchlassen.
        self._rate_per_minute = rate_per_minute
        self._cancelled = False

    def cancel(self) -> None:
        """Bricht den laufenden Lauf ab (kooperativ).

        Angestossene Abrufe laufen noch zu Ende, es werden aber keine neuen mehr
        begonnen. Die bis dahin gemeldeten Funde bleiben erhalten - der Sinn des
        Abbruchs ist ja, sich das Zwischenergebnis anzusehen.
        """
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """True, wenn der Lauf abgebrochen wurde."""
        return self._cancelled

    async def scan(
        self,
        source: str,
        *,
        on_pages: Callable[[int], None],
        on_finding: Callable[[ImageFinding], None],
        on_log: Callable[[str], None],
        on_progress: ProgressCallback | None = None,
        on_resolved: Callable[[str], None] | None = None,
        proxy: str = "",
        min_image_size: int = 0,
        render: bool = False,
        respect_robots: bool = True,
        accept_consent: bool = True,
    ) -> None:
        self._min_size = min_image_size
        self._cancelled = False
        headers = {"User-Agent": _USER_AGENT}
        async with httpx.AsyncClient(
            verify=False,
            follow_redirects=True,
            timeout=self._timeout,
            headers=headers,
            proxy=proxy.strip() or None,
        ) as client:
            # Last-Hinweis frueh ins Protokoll: ohne Limit ist die Rate allein
            # davon abhaengig, wie schnell das Ziel antwortet.
            if self._rate_per_minute > 0:
                on_log(t("log.rate_on", count=self._rate_per_minute))
            else:
                parallel = self._page_concurrency + self._image_concurrency
                on_log(t("log.rate_off", count=parallel))

            # Nur beim Rendern relevant: ohne Browser gibt es kein Banner.
            if render:
                on_log(t("log.consent_on") if accept_consent else t("log.consent_off"))

            on_log(t("log.loading_sitemap", source=source))
            pages = await load_sitemap(
                client, source, on_log=on_log, on_resolved=on_resolved
            )
            on_pages(len(pages))
            on_log(t("log.pages_found", count=len(pages)))
            if self._cancelled:  # waehrend des Sitemap-Ladens abgebrochen
                on_log(t("log.scan_cancelled"))
                return

            # robots.txt gilt fuer die SEITEN. Bilder werden bewusst nicht geprueft:
            # sie liegen oft auf einer CDN-Domain mit eigener robots.txt, und wer die
            # Seite ausliefern darf, liefert das Bild ohnehin mit aus.
            if respect_robots:
                robots = RobotsChecker()
                await robots.load(client, pages[0] if pages else source)
                allowed = [url for url in pages if robots.is_allowed(url)]
                blocked = len(pages) - len(allowed)
                if blocked:
                    on_log(t("log.robots_blocked", blocked=blocked, total=len(pages)))
                    pages = allowed
                    on_pages(len(pages))
                else:
                    on_log(t("log.robots_clear"))
            else:
                on_log(t("log.robots_ignored"))

            # Pipeline: sobald eine Seite ihre Bilder liefert, werden sie SOFORT
            # geprueft (kein Sammel-Barrier vor der Bildpruefung) -> die Tabelle
            # streamt live, waehrend noch gecrawlt wird.
            page_sem = asyncio.Semaphore(self._page_concurrency)
            image_sem = asyncio.Semaphore(self._image_concurrency)
            # Gewartet wird INNERHALB der Semaphore: so warten hoechstens
            # `concurrency` Tasks am Limiter, der Rest haengt am Semaphore -
            # sonst wuerden sich tausende Bild-Tasks vorab Slots reservieren.
            limiter = RateLimiter(self._rate_per_minute)
            seen: set[str] = set()
            seen_lock = asyncio.Lock()
            image_tasks: list[asyncio.Task[None]] = []
            pages_done = 0
            skipped = 0
            total_pages = len(pages)
            renderer: PageRenderer | None = None

            async def check_image(image_url: str, page_url: str) -> None:
                nonlocal skipped
                if self._cancelled:
                    return
                async with image_sem:
                    if self._cancelled:  # in der Warteschlange abgebrochen
                        return
                    await limiter.acquire()
                    finding = await self._check_image(client, image_url, page_url)
                if finding is None:  # zu klein -> uebersprungen
                    skipped += 1
                    return
                on_finding(finding)
                if finding.verdict is Verdict.ERROR and finding.error:
                    on_log(t("log.image_failed", reason=finding.error, url=image_url))

            async def scan_page(page_url: str) -> None:
                nonlocal pages_done
                if self._cancelled:
                    return
                async with page_sem:
                    if self._cancelled:  # in der Warteschlange abgebrochen
                        return
                    await limiter.acquire()
                    try:
                        images = await fetch_page_images(client, page_url)
                    except Exception as exc:  # noqa: BLE001 - kaputte Seite darf den Lauf nicht killen
                        on_log(t("log.page_failed", reason=_failure_reason(exc), url=page_url))
                        images = []
                    if renderer is not None:
                        # Hybrid: die per JS ins (Shadow-)DOM gerenderten Bilder
                        # ergaenzen die Regex-Treffer (Union, Reihenfolge stabil).
                        # Das Rendering ist ein ZWEITER Zugriff auf dieselbe Seite
                        # und zaehlt darum eigenstaendig gegen das Limit.
                        await limiter.acquire()
                        try:
                            rendered = await renderer.image_urls(page_url)
                        except Exception as exc:  # noqa: BLE001 - Render darf den Lauf nicht killen
                            on_log(
                                t(
                                    "log.render_failed",
                                    reason=_failure_reason(exc),
                                    url=page_url,
                                )
                            )
                            rendered = []
                        if rendered:
                            images = list(dict.fromkeys(images + rendered))
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

            async with AsyncExitStack() as stack:
                if render:
                    renderer = await stack.enter_async_context(
                        PageRenderer(
                            timeout=self._timeout,
                            proxy=proxy,
                            accept_consent=accept_consent,
                        )
                    )
                    on_log(t("log.render_active"))
                await asyncio.gather(*(scan_page(page_url) for page_url in pages))
                if not self._cancelled:
                    on_log(t("log.images_found", count=len(seen)))
                if image_tasks:
                    await asyncio.gather(*image_tasks)
            if self._cancelled:
                on_log(t("log.scan_cancelled"))
                return
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
        has_c2pa, dst, generator, width, height = await asyncio.to_thread(
            _probe, data, content_type
        )
        if self._min_size > 0 and 0 < width < self._min_size:
            return None
        return ImageFinding(
            image_url, page_url, has_c2pa, dst, classify(dst, has_c2pa, generator),
            width=width, height=height, generator=generator,
        )

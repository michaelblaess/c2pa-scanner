"""Seiten-Vorschau: Full-Page-Screenshots per Playwright-Sidecar.

Eigenstaendige Playwright-Instanz nur fuer Screenshots (unabhaengig vom Scan-
Renderer). Der Browser wird lazy beim ersten Screenshot gestartet und fuer
weitere Aufrufe offen gehalten. Screenshots werden im Speicher UND persistent
auf Disk gecacht (viele Bilder teilen dieselbe Seite). Uebernommen aus
sitemap-tracker; hier full_page=True (die ganze Seite), damit ein KI-Label an
beliebiger Position sichtbar wird.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from c2pa_scanner.infrastructure.consent import accept_consent

# Fortschritts-Callback: bekommt einen Phasen-Schluessel ("navigate",
# "consent", "render", "capture"), den die UI uebersetzt und anzeigt.
PhaseCallback = Callable[[str], None]

# Viewport-Breite fuer das Rendern; die Hoehe bestimmt full_page selbst.
_VIEWPORT = {"width": 1280, "height": 900}

# Persistenter Cache im User-Verzeichnis (neben settings.json/history.json).
CACHE_DIR = Path.home() / ".c2pa-scanner" / "preview-cache"

# TTL-Fallback: nach Ablauf wird der Screenshot neu erzeugt.
_TTL_SECONDS = 14 * 24 * 3600


class PreviewService:
    """Erzeugt Full-Page-Seiten-Screenshots ueber eine eigene Playwright-Instanz."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_seconds: int = _TTL_SECONDS,
        proxy: str = "",
        accept_consent: bool = True,
    ) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._mem: dict[str, bytes] = {}
        self._lock = asyncio.Lock()
        self._cache_dir = cache_dir or CACHE_DIR
        self._ttl = ttl_seconds
        self._proxy = proxy.strip()
        self._accept_consent = accept_consent

    async def capture(
        self, url: str, image_url: str = "", on_phase: PhaseCallback | None = None
    ) -> bytes | None:
        """Liefert einen Viewport-Screenshot der Seite, zum Bild gescrollt.

        Statt der ganzen Seite wird zum konkreten Fund-Bild gescrollt (zentriert)
        und nur der sichtbare Ausschnitt fotografiert - lesbar, um zu pruefen, ob
        ein KI-Label auf/an dem Bild dargestellt wird.

        Args:
            url:
                Die zu fotografierende Seiten-URL.
            image_url:
                URL des Fund-Bilds, zu dem gescrollt wird (leer = Seitenanfang).
            on_phase:
                Optionaler Callback je Schritt ("navigate", "consent",
                "render", "capture"); bei Cache-Treffern NICHT gerufen.

        Returns:
            PNG-Bilddaten oder None, wenn der Screenshot fehlschlaegt.
        """
        # Das Consent-Verhalten gehoert in den Schluessel: mit und ohne bestaetigtes
        # Banner sieht dieselbe Seite verschieden aus. Nebeneffekt und ausdruecklich
        # gewollt - Aufnahmen aus der Zeit, als das Banner stehen blieb, werden nicht
        # mehr getroffen und der Fehler klebt nicht wochenlang im Zwischenspeicher.
        key = f"{url}\n{image_url}\nconsent={int(self._accept_consent)}"
        cached = self._mem.get(key)
        if cached is not None:
            return cached

        async with self._lock:
            cached = self._mem.get(key)
            if cached is not None:
                return cached

            disk = self._load_disk(key)
            if disk is not None:
                self._mem[key] = disk
                return disk

            try:
                browser = await self._ensure_browser()
                page = await browser.new_page(viewport=_VIEWPORT, ignore_https_errors=True)
                try:
                    self._emit(on_phase, "navigate")
                    await page.goto(url, wait_until="load", timeout=20000)
                    await self._prepare_page(page, on_phase)
                    if image_url:
                        await self._scroll_to_image(page, image_url)
                    self._emit(on_phase, "capture")
                    data: bytes = await page.screenshot(type="png")
                finally:
                    await page.close()
            except Exception:  # noqa: BLE001 - Vorschau darf nie crashen
                return None

        self._mem[key] = data
        self._save_disk(key, data)
        return data

    @staticmethod
    async def _scroll_to_image(page: Any, image_url: str) -> None:
        """Scrollt das <img> mit der passenden Quelle zentriert in den Viewport."""
        with contextlib.suppress(Exception):
            await page.evaluate(
                """(url) => {
                    const norm = (u) => { try { return new URL(u, location.href).href; }
                                          catch (e) { return u; } };
                    const target = norm(url);
                    const base = (url.split('#')[0].split('?')[0].split('/').pop()) || '';
                    const imgs = Array.from(document.querySelectorAll('img'));
                    let el = imgs.find((i) => norm(i.currentSrc || i.src) === target);
                    if (!el && base) {
                        el = imgs.find((i) => (i.currentSrc || i.src || '').includes(base));
                    }
                    if (el) { el.scrollIntoView({block: 'center', inline: 'center'}); }
                }""",
                image_url,
            )
            await page.wait_for_timeout(400)

    @staticmethod
    def _emit(on_phase: PhaseCallback | None, phase: str) -> None:
        if on_phase is None:
            return
        with contextlib.suppress(Exception):
            on_phase(phase)

    async def _prepare_page(self, page: Any, on_phase: PhaseCallback | None = None) -> None:
        """Consent akzeptieren + Lazy-Loading durch Scrollen ausloesen."""
        if self._accept_consent:
            self._emit(on_phase, "consent")
            await accept_consent(page)
        self._emit(on_phase, "render")
        await self._trigger_lazy_loading(page)

    @staticmethod
    async def _trigger_lazy_loading(page: Any) -> None:
        """Scrollt die Seite durch und wartet, bis die Bilder geladen sind."""
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=8000)

        with contextlib.suppress(Exception):
            viewport_height = await page.evaluate("window.innerHeight")
            scroll_height = await page.evaluate("document.documentElement.scrollHeight")

            if scroll_height > viewport_height:
                current = 0
                while current < scroll_height:
                    current += viewport_height
                    await page.evaluate(f"window.scrollTo(0, {current})")
                    await page.wait_for_timeout(150)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(300)

            for _ in range(12):
                all_loaded = await page.evaluate(
                    """() => {
                        const imgs = Array.from(document.querySelectorAll('img'));
                        return imgs.every(i => i.complete && i.naturalWidth > 0);
                    }"""
                )
                if all_loaded:
                    break
                await page.wait_for_timeout(250)

            await page.wait_for_timeout(500)

    def _load_disk(self, url: str) -> bytes | None:
        """Laedt einen Screenshot von Disk, sofern das TTL noch nicht abgelaufen ist."""
        png = self._png_path(url)
        meta = self._meta_path(url)
        if not png.is_file() or not meta.is_file():
            return None
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            captured = float(info.get("captured_at", 0))
        except (ValueError, OSError):
            return None
        if (time.time() - captured) > self._ttl:
            return None
        try:
            return png.read_bytes()
        except OSError:
            return None

    def _save_disk(self, url: str, data: bytes) -> None:
        """Schreibt Screenshot + Meta-Sidecar best-effort auf Disk."""
        with contextlib.suppress(OSError):
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._png_path(url).write_bytes(data)
            self._meta_path(url).write_text(
                json.dumps({"url": url, "captured_at": time.time()}), encoding="utf-8"
            )

    def _png_path(self, url: str) -> Path:
        return self._cache_dir / f"{self._key(url)}.png"

    def _meta_path(self, url: str) -> Path:
        return self._cache_dir / f"{self._key(url)}.json"

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    async def _ensure_browser(self) -> Any:
        """Startet den Sidecar-Browser beim ersten Aufruf."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
                proxy={"server": self._proxy} if self._proxy else None,
            )
        return self._browser

    async def close(self) -> None:
        """Schliesst Browser und Playwright-Instanz best-effort.

        Nimmt dasselbe Lock wie capture(), damit der Browser nicht mitten in
        einem laufenden Screenshot-Call geschlossen wird. Sonst faellt close()
        dem noch offenen Protokoll-Call in den Ruecken und dessen Playwright-
        Future bleibt mit TargetClosedError unabgeholt ("Future exception was
        never retrieved" beim Beenden).
        """
        async with self._lock:
            if self._browser is not None:
                with contextlib.suppress(Exception):
                    await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                with contextlib.suppress(Exception):
                    await self._playwright.stop()
                self._playwright = None

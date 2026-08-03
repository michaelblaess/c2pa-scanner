"""Optionales Browser-Rendering (Playwright) fuer JS-gerenderte Bilder.

Die Regex-Extraktion aus web.py findet nur Bild-URLs, die im ausgelieferten
Server-HTML stehen. Baut eine Seite ihre Bilder erst clientseitig per JS ins
(Shadow-)DOM (z.B. lazy per fetch, JS-gesetzte background-images), fehlen diese.
Der PageRenderer laedt die Seite in einem echten Chromium (Playwright), wartet
auf das gerenderte DOM und sammelt die Bild-URLs - inkl. offener Shadow-Roots
und CSS-background-images. Rendering ist teuer und daher zuschaltbar.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any
from urllib.parse import urldefrag, urljoin

from c2pa_scanner.infrastructure.consent import accept_consent

# JS-Sammler: laeuft im Seitenkontext, geht das DOM inkl. offener Shadow-Roots
# durch und liefert alle <img>-Quellen sowie CSS-background-image-URLs.
_COLLECT_JS = r"""() => {
  const urls = new Set();
  const add = (u) => { if (u) urls.add(u); };
  const bgUrls = (value) => {
    if (!value || value === 'none') return;
    const re = /url\((['"]?)(.*?)\1\)/g;
    let m;
    while ((m = re.exec(value)) !== null) { add(m[2]); }
  };
  const walk = (root) => {
    const nodes = root.querySelectorAll('*');
    for (const el of nodes) {
      if (el.tagName === 'IMG') { add(el.currentSrc || el.src); }
      if (el.tagName === 'SOURCE' && el.srcset) {
        el.srcset.split(',').forEach((part) => add(part.trim().split(/\s+/)[0]));
      }
      try { bgUrls(getComputedStyle(el).backgroundImage); } catch (e) { /* ignore */ }
      if (el.shadowRoot) { walk(el.shadowRoot); }
    }
  };
  walk(document);
  return Array.from(urls);
}"""


class PageRenderer:
    """Rendert Seiten mit einem gemeinsam genutzten Chromium und liefert Bild-URLs.

    Als Async-Context-Manager verwenden: startet Playwright + Browser einmal,
    schliesst beide beim Verlassen.
    """

    def __init__(
        self,
        *,
        timeout: float,
        proxy: str = "",
        headless: bool = True,
        accept_consent: bool = True,
    ) -> None:
        self._timeout = timeout
        self._proxy = proxy.strip()
        self._headless = headless
        self._accept_consent = accept_consent
        self._pw: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> PageRenderer:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        proxy = {"server": self._proxy} if self._proxy else None
        self._browser = await self._pw.chromium.launch(
            headless=self._headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=proxy,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()

    async def image_urls(self, page_url: str) -> list[str]:
        """Rendert page_url und liefert die absoluten, deduplizierten Bild-URLs."""
        if self._browser is None:
            return []
        page = await self._browser.new_page()
        try:
            await page.goto(
                page_url, wait_until="networkidle", timeout=int(self._timeout * 1000)
            )
            # Hinter einem Consent-Banner bleiben Bilder haeufig ungeladen (die
            # Seite schaltet sie erst nach der Zustimmung frei) - erst zustimmen,
            # dann einsammeln.
            if self._accept_consent:
                await accept_consent(page)
            raw: list[str] = await page.evaluate(_COLLECT_JS)
        finally:
            await page.close()

        result: list[str] = []
        seen: set[str] = set()
        for candidate in raw:
            if not candidate or candidate.startswith("data:"):
                continue
            absolute = urldefrag(urljoin(page_url, candidate))[0]
            if absolute.lower().endswith(".svg"):
                continue
            if absolute not in seen:
                seen.add(absolute)
                result.append(absolute)
        return result

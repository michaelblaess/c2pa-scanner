"""Integrationstest: bricht ein laufender Scan wirklich ab - und bleiben die Funde?

Der Abbruch ist kooperativ: der Dienst startet keine neuen Abrufe mehr, bereits
laufende beendet er. Geprueft wird deshalb, dass ein abgebrochener Lauf NICHT
alle Seiten der Sitemap holt und die bis dahin gemeldeten Funde erhalten bleiben.
Ohne die Abbruchpruefungen im Dienst laeuft der Scan komplett durch - dann faellt
der Test.
"""

from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from c2pa_scanner.domain.models import ImageFinding
from c2pa_scanner.services.sitemap_scan import SitemapScanService

_PAGE_COUNT = 12

# Kleinstes gueltiges PNG (1x1, transparent) - Inhalt ist egal, es geht um den Ablauf.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class _Handler(BaseHTTPRequestHandler):
    """Sitemap mit Seiten, die je ein eigenes Bild einbinden."""

    pages_served = 0
    lock = threading.Lock()

    def do_GET(self) -> None:  # noqa: N802 - von BaseHTTPRequestHandler vorgegeben
        host = f"http://{self.headers['Host']}"
        if self.path == "/sitemap.xml":
            urls = "".join(f"<url><loc>{host}/seite-{i}</loc></url>" for i in range(_PAGE_COUNT))
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
            ).encode()
            content_type = "application/xml"
        elif self.path.endswith(".png"):
            body = _PNG
            content_type = "image/png"
        else:
            with _Handler.lock:
                _Handler.pages_served += 1
            name = self.path.strip("/")
            body = f'<html><body><img src="{host}/{name}.png"></body></html>'.encode()
            content_type = "text/html"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Unterdrueckt die Server-Logzeilen im Testlauf."""


def _run(cancel_after_pages: int | None) -> tuple[int, list[ImageFinding], bool]:
    """Faehrt einen Scan; bricht ihn ab, sobald so viele Seiten geholt wurden.

    Args:
        cancel_after_pages:
            Nach wie vielen ausgelieferten Seiten abgebrochen wird. None = gar nicht.

    Returns:
        (ausgelieferte Seiten, gemeldete Funde, Abbruch-Kennzeichen des Dienstes).
    """
    _Handler.pages_served = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    findings: list[ImageFinding] = []
    # Eine Seite zur Zeit und gedrosselt, damit der Abbruch mitten im Lauf greift.
    service = SitemapScanService(page_concurrency=1, image_concurrency=1, rate_per_minute=240)

    async def watchdog() -> None:
        if cancel_after_pages is None:
            return
        for _ in range(400):  # hoechstens ~20 s
            if _Handler.pages_served >= cancel_after_pages:
                service.cancel()
                return
            await asyncio.sleep(0.05)

    async def run() -> None:
        watcher = asyncio.create_task(watchdog())
        await service.scan(
            f"{base}/sitemap.xml",
            on_pages=lambda n: None,
            on_finding=findings.append,
            on_log=lambda message: None,
            respect_robots=False,
        )
        watcher.cancel()

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
    return _Handler.pages_served, findings, service.cancelled


class TestScanCancel:
    def test_cancel_stops_the_run_early(self) -> None:
        """Nach dem Abbruch werden keine weiteren Seiten mehr geholt."""
        served, _findings, cancelled = _run(cancel_after_pages=3)
        assert cancelled is True
        # Bereits angestossene Abrufe laufen aus, deshalb grosszuegige Schranke -
        # ein vollstaendiger Lauf haette alle Seiten geholt.
        assert served < _PAGE_COUNT, f"Lauf ging weiter: {served}/{_PAGE_COUNT} Seiten"

    def test_findings_survive_the_cancel(self) -> None:
        """Die vor dem Abbruch gemeldeten Funde bleiben erhalten."""
        _served, findings, cancelled = _run(cancel_after_pages=3)
        assert cancelled is True
        assert findings, "Der Teillauf hat keine Funde gemeldet"

    def test_uncancelled_run_is_complete(self) -> None:
        """Gegenprobe: ohne Abbruch laeuft derselbe Scan vollstaendig durch."""
        served, findings, cancelled = _run(cancel_after_pages=None)
        assert cancelled is False
        assert served == _PAGE_COUNT
        assert len(findings) == _PAGE_COUNT

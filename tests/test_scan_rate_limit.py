"""Integrationstest: greift das Rate-Limit im echten Scan-Pfad?

Der Unit-Test in test_rate_limit.py prueft nur den Limiter selbst. Hier laeuft
ein vollstaendiger Scan gegen einen lokalen HTTP-Server - einmal gedrosselt,
einmal nicht. Faellt die Verdrahtung im Service weg, sind beide Laeufe gleich
schnell und der Test schlaegt fehl.
"""

from __future__ import annotations

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from c2pa_scanner.services.sitemap_scan import SitemapScanService

_PAGE_COUNT = 5


class _Handler(BaseHTTPRequestHandler):
    """Liefert eine Sitemap mit fuenf bildlosen Seiten."""

    def do_GET(self) -> None:  # noqa: N802 - von BaseHTTPRequestHandler vorgegeben
        if self.path == "/sitemap.xml":
            host = f"http://{self.headers['Host']}"
            urls = "".join(f"<url><loc>{host}/seite-{i}</loc></url>" for i in range(_PAGE_COUNT))
            body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
            ).encode()
            content_type = "application/xml"
        else:
            body = b"<html><body>ohne Bilder</body></html>"
            content_type = "text/html"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Unterdrueckt die Server-Logzeilen im Testlauf."""


def _scan_seconds(rate_per_minute: int) -> float:
    """Startet den Server, misst einen kompletten Scan und raeumt wieder auf."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    pages_seen: list[int] = []

    async def run() -> None:
        await SitemapScanService(rate_per_minute=rate_per_minute).scan(
            f"{base}/sitemap.xml",
            on_pages=pages_seen.append,
            on_finding=lambda finding: None,
            on_log=lambda message: None,
            respect_robots=False,
        )

    try:
        start = time.monotonic()
        asyncio.run(run())
        elapsed = time.monotonic() - start
    finally:
        server.shutdown()
        server.server_close()

    assert pages_seen and pages_seen[0] == _PAGE_COUNT, "Sitemap wurde nicht gelesen"
    return elapsed


class TestScanRateLimit:
    def test_unlimited_scan_is_fast(self) -> None:
        """Referenzlauf: ohne Limit ist der Scan lokal in Sekundenbruchteilen durch."""
        assert _scan_seconds(0) < 1.0

    def test_rate_limit_slows_the_scan_down(self) -> None:
        """1200/Minute = 50 ms Abstand, fuenf Seiten warten also >= 4 Intervalle."""
        assert _scan_seconds(1200) >= 0.15

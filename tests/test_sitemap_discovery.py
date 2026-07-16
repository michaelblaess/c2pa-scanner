"""Auto-Discovery der Sitemap (robots.txt + Standardpfade), offline gemockt."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from c2pa_scanner.infrastructure.sitemap import is_sitemap_url, load_sitemap

_URLSET = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://example.com/a</loc></url>"
    "<url><loc>https://example.com/b</loc></url>"
    "</urlset>"
)


async def _discover(routes: dict[str, tuple[int, str]], source: str) -> list[str]:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(str(request.url), (404, "<html>Not Found</html>"))
        return httpx.Response(status, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await load_sitemap(client, source)


class TestDiscovery:
    def test_is_sitemap_url(self) -> None:
        assert is_sitemap_url("https://example.com/sitemap.xml")
        assert not is_sitemap_url("https://example.com")

    def test_discovers_via_robots(self) -> None:
        routes = {
            "https://example.com/robots.txt": (200, "Sitemap: https://example.com/sm/custom.xml"),
            "https://example.com/sm/custom.xml": (200, _URLSET),
        }
        pages = asyncio.run(_discover(routes, "https://example.com"))
        assert pages == ["https://example.com/a", "https://example.com/b"]

    def test_discovers_via_common_path(self) -> None:
        # robots.txt ohne Sitemap-Zeile -> Fallback auf Standardpfad.
        routes = {
            "https://example.com/robots.txt": (200, "User-agent: *"),
            "https://example.com/sitemap/sitemap.xml": (200, _URLSET),
        }
        pages = asyncio.run(_discover(routes, "https://example.com"))
        assert len(pages) == 2

    def test_raises_when_nothing_found(self) -> None:
        with pytest.raises(ValueError, match="Keine Sitemap gefunden"):
            asyncio.run(_discover({}, "https://example.com"))

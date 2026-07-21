"""Sichert die schonenden Vorgabewerte ab.

Diese Tests halten die Zusicherung fest, dass ein Lauf ohne weitere Angaben
gedrosselt ist. Wird ein Vorgabewert versehentlich auf "ungebremst" gesetzt,
schlagen sie fehl.
"""

from __future__ import annotations

from c2pa_scanner.__main__ import build_parser
from c2pa_scanner.infrastructure.rate_limit import RateLimiter
from c2pa_scanner.services.sitemap_scan import SitemapScanService


class TestSafeDefaults:
    def test_service_is_throttled_by_default(self) -> None:
        assert SitemapScanService()._rate_per_minute == 60

    def test_service_limiter_is_active_by_default(self) -> None:
        assert RateLimiter(SitemapScanService()._rate_per_minute).enabled is True

    def test_cli_scan_is_throttled_by_default(self) -> None:
        args = build_parser().parse_args(["scan", "https://example.com/sitemap.xml"])
        assert args.rate_limit == 60

    def test_cli_allows_turning_the_limit_off(self) -> None:
        args = build_parser().parse_args(
            ["scan", "https://example.com/sitemap.xml", "--rate-limit", "0"]
        )
        assert args.rate_limit == 0

    def test_cli_requires_disclaimer_acknowledgement(self) -> None:
        """Der Hinweis gilt erst als bestaetigt, wenn das Flag gesetzt wurde."""
        args = build_parser().parse_args(["scan", "https://example.com/sitemap.xml"])
        assert args.accept_disclaimer is False

    def test_robots_is_respected_by_default(self) -> None:
        args = build_parser().parse_args(["scan", "https://example.com/sitemap.xml"])
        assert args.ignore_robots is False

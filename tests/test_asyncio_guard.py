"""Tests fuer den Playwright-Shutdown-Guard (verwaiste TargetClosedError-Futures)."""

from __future__ import annotations

import asyncio

from c2pa_scanner.infrastructure.asyncio_guard import (
    _is_target_closed,
    install_playwright_shutdown_guard,
)


class _FakeTargetClosed(Exception):
    pass


# Modul faelschen, damit _is_target_closed den playwright-Herkunftscheck besteht.
_FakeTargetClosed.__name__ = "TargetClosedError"
_FakeTargetClosed.__module__ = "playwright._impl._errors"


class _OtherError(Exception):
    pass


def test_is_target_closed_matches_only_playwright() -> None:
    assert _is_target_closed(_FakeTargetClosed("closed"))
    assert not _is_target_closed(_OtherError("boom"))
    assert not _is_target_closed(None)


def test_guard_swallows_target_closed_but_passes_others() -> None:
    async def scenario() -> tuple[bool, bool]:
        loop = asyncio.get_running_loop()
        seen: list[str] = []
        loop.set_exception_handler(lambda _l, ctx: seen.append(ctx.get("message", "")))
        install_playwright_shutdown_guard(loop)

        # TargetClosedError wird geschluckt ...
        loop.call_exception_handler(
            {"message": "Future exception was never retrieved", "exception": _FakeTargetClosed("x")}
        )
        swallowed = len(seen) == 0
        # ... eine andere Exception wird an den vorherigen Handler durchgereicht.
        loop.call_exception_handler({"message": "andere", "exception": _OtherError("x")})
        passed = seen == ["andere"]
        return swallowed, passed

    swallowed, passed = asyncio.run(scenario())
    assert swallowed
    assert passed


def test_guard_falls_back_to_default_handler_without_previous() -> None:
    # Ohne vorher gesetzten Handler darf install() nicht crashen und Nicht-Target-
    # Closed-Kontexte an den Default-Handler weiterreichen (kein Fehler).
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        install_playwright_shutdown_guard(loop)
        loop.call_exception_handler({"message": "x", "exception": _FakeTargetClosed("x")})

    asyncio.run(scenario())

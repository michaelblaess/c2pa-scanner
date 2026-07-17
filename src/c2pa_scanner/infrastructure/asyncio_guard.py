"""Asyncio-Guard gegen verwaiste Playwright-Futures beim Beenden.

Beim Schliessen der App bricht der Preview-Sidecar bzw. der Scan-Renderer einen
noch laufenden Browser-Call (`page.goto`/`screenshot`) ab. Playwright resolved
dessen internen Protokoll-Future danach mit `TargetClosedError`, aber der
gecancelte Worker holt sie nicht mehr ab - asyncio meldet das beim GC als
"Future exception was never retrieved". Diese eine, beim Shutdown strukturell
unvermeidbare Exception fangen wir gezielt ab; alles andere geht unveraendert an
den vorherigen Handler.
"""

from __future__ import annotations

import asyncio
from typing import Any


def _is_target_closed(exc: BaseException | None) -> bool:
    """True, wenn exc Playwrights TargetClosedError ist (ohne Playwright zu importieren)."""
    if exc is None:
        return False
    cls = type(exc)
    return cls.__name__ == "TargetClosedError" and cls.__module__.startswith("playwright")


def install_playwright_shutdown_guard(loop: asyncio.AbstractEventLoop) -> None:
    """Registriert einen Exception-Handler, der beim Beenden nur TargetClosedError schluckt.

    Args:
        loop:
            Der laufende Event-Loop, auf dem der Handler installiert wird.
    """
    previous = loop.get_exception_handler()

    def handler(loop_: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if _is_target_closed(context.get("exception")):
            return
        if previous is not None:
            previous(loop_, context)
        else:
            loop_.default_exception_handler(context)

    loop.set_exception_handler(handler)

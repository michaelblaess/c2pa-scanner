"""Tests fuer den Preview-Sidecar (Shutdown-Verhalten)."""

from __future__ import annotations

import asyncio

from c2pa_scanner.services.preview_service import PreviewService


def test_close_waits_for_active_capture_lock() -> None:
    # close() muss dasselbe Lock nehmen wie capture(): laeuft gerade ein
    # Screenshot, darf der Browser nicht darunter weggeschlossen werden (sonst
    # bleibt dessen Playwright-Future mit TargetClosedError unabgeholt).
    async def scenario() -> bool:
        svc = PreviewService()
        await svc._lock.acquire()  # simuliert ein laufendes capture()
        task = asyncio.create_task(svc.close())
        await asyncio.sleep(0.05)
        blocked = not task.done()  # close() wartet am Lock
        svc._lock.release()
        await asyncio.wait_for(task, timeout=1)
        return blocked and task.done()

    assert asyncio.run(scenario())


def test_close_is_idempotent_without_browser() -> None:
    # Ohne je gestarteten Browser laeuft close() sofort und ohne Fehler durch.
    async def scenario() -> None:
        await PreviewService().close()

    asyncio.run(scenario())

"""Erkennung eines vorgeschalteten Proxy-/Auth-Gateways (z.B. Zscaler) oder SSO.

Ein Gateway faengt Anfragen ab und leitet per Redirect auf einen eigenen Host um
(z.B. gateway.zscloud.net, login.microsoftonline.com). Landet die Start-URL nach
Redirects auf einer FREMDEN Registrable-Domain, ist ein Gateway vorgeschaltet und
der Scan liefert keine echten Seiten-Bilder.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class ProxyDetection:
    """Ergebnis der Proxy-/Gateway-Erkennung."""

    host: str
    final_url: str


def _registrable(host: str) -> str:
    """Vereinfachte Registrable-Domain (die letzten zwei Labels)."""
    host = host.lower().strip(".")
    if not host or host.replace(".", "").isdigit():
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


async def probe_proxy(
    start_url: str, *, timeout: float = 30.0, proxy: str = ""
) -> ProxyDetection | None:
    """Prueft, ob die Start-URL auf eine fremde Registrable-Domain umgeleitet wird.

    Gibt bei erkanntem Gateway eine ProxyDetection zurueck, sonst None (auch bei
    Netzwerkfehlern - die meldet dann der eigentliche Scan).
    """
    start_host = (urlparse(start_url).hostname or "").lower()
    if not start_host:
        return None
    start_reg = _registrable(start_host)
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, verify=False, proxy=proxy.strip() or None
        ) as client:
            response = await client.get(start_url)
    except Exception:  # noqa: BLE001 - Netzwerkfehler ist kein Proxy-Urteil
        return None
    if not response.history:
        return None
    final_host = (urlparse(str(response.url)).hostname or "").lower()
    if final_host and _registrable(final_host) != start_reg:
        return ProxyDetection(host=final_host, final_url=str(response.url))
    return None

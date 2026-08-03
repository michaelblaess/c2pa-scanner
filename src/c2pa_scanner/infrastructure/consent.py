"""Cookie-Consent-Banner automatisch akzeptieren (Usercentrics/OneTrust/Cookiebot).

Warum ein eigenes Modul: Der Consent-Manager wird per asynchronem Script
nachgeladen und ist beim ``load``-Ereignis der Seite noch NICHT initialisiert.
Ein einmaliger Aufruf direkt nach ``goto`` findet ``window.UC_UI`` deshalb gar
nicht vor und tut nichts - das Banner bleibt im Screenshot stehen. Gemessen an
einer Usercentrics-3.104-Seite: direkt nach ``load`` fehlt die Schnittstelle,
rund 0,2 s spaeter ist sie da. Darum wird hier gewartet, statt einmal zu raten.

Gewartet wird nur, wenn die Seite ueberhaupt Anzeichen fuer einen Consent-
Manager zeigt (Script-URL oder bekannter Container). Seiten ohne Banner kosten
so keine Wartezeit.

Alle Funktionen sind best-effort: ein Fehlschlag darf weder Scan noch Vorschau
abbrechen.
"""

from __future__ import annotations

import contextlib
from typing import Any

# Wartezeit, bis der Consent-Manager initialisiert ist (nur wenn einer erwartet wird).
DEFAULT_TIMEOUT_MS = 6000

# Pause nach dem Akzeptieren: die freigeschalteten Skripte laden nach.
_SETTLE_MS = 1500

# Abstand der Versuche waehrend des Wartens.
_POLL_MS = 200

# Gibt es auf der Seite ueberhaupt einen Consent-Manager? Geprueft werden die
# Skript-URLs und die bekannten Container - beides steht schon im Server-HTML,
# also lange bevor die JS-Schnittstelle existiert.
_EXPECTED_JS = """() => {
    const hasScript = Array.from(document.querySelectorAll('script[src], link[href]'))
        .some((el) => /usercentrics|onetrust|cookiebot|cookielaw/i.test(
            el.src || el.href || ''));
    const hasHost = !!document.querySelector(
        '#usercentrics-cmp-ui, #usercentrics-root, [id^=usercentrics], '
        + '#onetrust-banner-sdk, #onetrust-consent-sdk, #CybotCookiebotDialog');
    const hasApi = !!(window.UC_UI || window.__ucCmp || window.OneTrust || window.Cookiebot);
    return hasScript || hasHost || hasApi;
}"""

# Bekannte Programmierschnittstellen der Consent-Manager. Usercentrics kennt in
# Version 2 wie in Version 3 ``UC_UI``; ``__ucCmp`` ist der neuere Zugang.
_API_JS = """async () => {
    const uc = window.UC_UI;
    if (uc && typeof uc.acceptAllConsents === 'function') {
        await uc.acceptAllConsents();
        if (typeof uc.closeCMP === 'function') { uc.closeCMP(); }
        return 'usercentrics';
    }
    const cmp = window.__ucCmp;
    if (cmp && typeof cmp.acceptAllConsents === 'function') {
        await cmp.acceptAllConsents();
        return 'usercentrics';
    }
    if (window.OneTrust && typeof window.OneTrust.AllowAll === 'function') {
        window.OneTrust.AllowAll();
        return 'onetrust';
    }
    const cb = window.Cookiebot;
    if (cb && typeof cb.submitCustomConsent === 'function') {
        cb.submitCustomConsent(true, true, true);
        return 'cookiebot';
    }
    return '';
}"""

# Rueckfallebene: den Zustimmen-Knopf klicken. Bewusst NUR innerhalb der
# bekannten Consent-Container gesucht (auch im Schatten-DOM), damit auf der
# Seite kein beliebiger Knopf mit aehnlicher Beschriftung getroffen wird.
_BUTTON_JS = """() => {
    const hosts = Array.from(document.querySelectorAll(
        '#usercentrics-cmp-ui, #usercentrics-root, [id^=usercentrics], '
        + '#onetrust-banner-sdk, #onetrust-consent-sdk, #CybotCookiebotDialog'));
    const wanted = /(accept.?all|alle[s]? akzeptieren|allow all|zustimmen|einverstanden)/i;
    const known = ['uc-accept-all-button', 'onetrust-accept-btn-handler',
                   'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
                   'CybotCookiebotDialogBodyButtonAccept'];
    const visible = (el) => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };
    for (const host of hosts) {
        const roots = [host];
        if (host.shadowRoot) { roots.push(host.shadowRoot); }
        for (const root of roots) {
            const buttons = Array.from(root.querySelectorAll('button, [role=button], a'));
            let btn = buttons.find((b) => known.includes(b.id)
                || known.includes(b.getAttribute('data-testid') || ''));
            if (!btn) {
                btn = buttons.find((b) => wanted.test((b.innerText || '').trim()));
            }
            if (btn && visible(btn)) { btn.click(); return 'button'; }
        }
    }
    return '';
}"""


async def accept_consent(page: Any, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> str:
    """Akzeptiert ein Cookie-Consent-Banner, sobald dessen Manager bereit ist.

    Args:
        page:
            Bereits navigierte Playwright-Seite.
        timeout_ms:
            Obergrenze fuer das Warten auf den Consent-Manager. Wird nur
            ausgeschoepft, wenn die Seite einen Manager erwarten laesst.

    Returns:
        Name des behandelten Managers ("usercentrics", "onetrust", "cookiebot",
        "button") oder ein leerer Text, wenn nichts zu tun war.
    """
    with contextlib.suppress(Exception):
        if not await page.evaluate(_EXPECTED_JS):
            return ""

        waited = 0
        while True:
            handled = await _try_accept(page)
            if handled:
                await page.wait_for_timeout(_SETTLE_MS)
                return handled
            if waited >= timeout_ms:
                return ""
            await page.wait_for_timeout(_POLL_MS)
            waited += _POLL_MS
    return ""


async def _try_accept(page: Any) -> str:
    """Ein Versuch: erst die Schnittstelle, dann der Knopf im Banner."""
    result = ""
    with contextlib.suppress(Exception):
        result = str(await page.evaluate(_API_JS) or "")
    if result:
        return result
    with contextlib.suppress(Exception):
        result = str(await page.evaluate(_BUTTON_JS) or "")
    return result

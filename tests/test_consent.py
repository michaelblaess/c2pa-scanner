"""Tests fuer das automatische Bestaetigen von Cookie-Consent-Bannern.

Der Kern ist das Warten: der Consent-Manager wird per asynchronem Script
nachgeladen und ist beim ``load``-Ereignis noch nicht da. Ein einmaliger Versuch
direkt nach dem Laden geht darum ins Leere - genau das war der Fehler, den diese
Tests festhalten. Ein echter Browser ist dafuer nicht noetig: nachgestellt wird
eine Seite, die ihre Schnittstelle erst nach einigen Versuchen bereitstellt.
"""

from __future__ import annotations

import asyncio

from c2pa_scanner.infrastructure import consent
from c2pa_scanner.services.preview_service import PreviewService


class FakePage:
    """Minimale Playwright-Seite: beantwortet die drei JS-Bausteine des Moduls.

    Args:
        has_cmp:
            Zeigt die Seite Anzeichen fuer einen Consent-Manager?
        api_after:
            Nach wie vielen Versuchen die JS-Schnittstelle bereitsteht
            (None = nie).
        button_after:
            Nach wie vielen Versuchen der Zustimmen-Knopf klickbar ist
            (None = nie).
    """

    def __init__(
        self,
        has_cmp: bool = True,
        api_after: int | None = 0,
        button_after: int | None = None,
    ) -> None:
        self.has_cmp = has_cmp
        self.api_after = api_after
        self.button_after = button_after
        self.api_calls = 0
        self.button_calls = 0
        self.waited_ms = 0

    async def evaluate(self, script: str) -> object:
        if script is consent._EXPECTED_JS:
            return self.has_cmp
        if script is consent._API_JS:
            ready = self.api_after is not None and self.api_calls >= self.api_after
            self.api_calls += 1
            return "usercentrics" if ready else ""
        if script is consent._BUTTON_JS:
            ready = self.button_after is not None and self.button_calls >= self.button_after
            self.button_calls += 1
            return "button" if ready else ""
        raise AssertionError(f"unerwartetes Skript: {script[:40]}")

    async def wait_for_timeout(self, milliseconds: int) -> None:
        self.waited_ms += milliseconds


class TestAcceptConsent:
    def test_no_banner_returns_immediately(self) -> None:
        """Ohne Anzeichen fuer ein Banner wird nicht gewartet - das kostet sonst
        auf jeder bannerfreien Seite die volle Wartezeit."""
        page = FakePage(has_cmp=False)
        assert asyncio.run(consent.accept_consent(page)) == ""
        assert page.api_calls == 0
        assert page.waited_ms == 0

    def test_api_available_right_away(self) -> None:
        page = FakePage(api_after=0)
        assert asyncio.run(consent.accept_consent(page)) == "usercentrics"
        assert page.api_calls == 1

    def test_waits_for_a_late_consent_manager(self) -> None:
        """Der eigentliche Fehlerfall: die Schnittstelle kommt erst spaeter.

        Beim ersten Versuch fehlt sie noch. Wer nur einmal fragt, bekommt nichts
        und laesst das Banner stehen.
        """
        page = FakePage(api_after=3)
        assert asyncio.run(consent.accept_consent(page)) == "usercentrics"
        assert page.api_calls == 4, "es wurde nicht erneut versucht"

    def test_button_fallback_when_no_api(self) -> None:
        """Kennt die Seite keine Schnittstelle, wird der Knopf im Banner geklickt."""
        page = FakePage(api_after=None, button_after=1)
        assert asyncio.run(consent.accept_consent(page)) == "button"

    def test_gives_up_after_the_timeout(self) -> None:
        """Kommt nie ein Manager, wird nach der Frist aufgegeben - nicht endlos."""
        page = FakePage(api_after=None, button_after=None)
        assert asyncio.run(consent.accept_consent(page, timeout_ms=600)) == ""
        # 600 ms Frist bei 200 ms Abstand: vier Versuche (0/200/400/600 ms).
        assert page.api_calls == 4
        assert page.waited_ms == 600


class TestPreviewServiceWiring:
    """Die Einstellung muss bis in die Vorschau durchschlagen."""

    def test_consent_is_accepted_when_enabled(self) -> None:
        page = FakePage(api_after=0)
        service = PreviewService(accept_consent=True)
        service._trigger_lazy_loading = _noop  # Scrollen ist hier nicht Gegenstand
        asyncio.run(service._prepare_page(page))
        assert page.api_calls == 1

    def test_consent_is_skipped_when_disabled(self) -> None:
        page = FakePage(api_after=0)
        service = PreviewService(accept_consent=False)
        service._trigger_lazy_loading = _noop
        asyncio.run(service._prepare_page(page))
        assert page.api_calls == 0, "Banner wurde trotz abgeschalteter Einstellung bestaetigt"


async def _noop(_page: object) -> None:
    """Ersetzt das Durchscrollen der Seite in den Verdrahtungstests."""

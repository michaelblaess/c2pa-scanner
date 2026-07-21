"""i18n - Einfache Internationalisierung ueber JSON-Sprachdateien.

Aufbau wie in den Schwester-Werkzeugen (sitemap-tracker, console-error-scanner):
je Sprache eine flache JSON-Datei unter ``locale/``, Zugriff ueber ``t()``.

Abweichung zu den aelteren Werkzeugen: Die Ausweichsprache ist Englisch, nicht
Deutsch. Das Projekt ist englischsprachig dokumentiert, und ein Haftungshinweis
in einer Sprache, die der Nutzer nicht liest, verfehlt seinen Zweck.
"""

from __future__ import annotations

import contextlib
import json
import locale
import logging
import os
from datetime import datetime
from importlib import resources

logger = logging.getLogger(__name__)

_strings: dict[str, str] = {}
_current_lang: str = "en"

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "en"


def detect_language() -> str:
    """Leitet die Startsprache aus der Systemumgebung ab.

    Nur beim allerersten Start relevant - danach steht die Sprache in den
    Einstellungen.

    Deutsch wird nur bei einer nachweislich deutschsprachigen Umgebung gewaehlt.
    Jeder andere Fall - unbekannte Sprache, leere Umgebung oder ein Fehler beim
    Auslesen (locale.getlocale() wirft auf manchen Systemen) - fuehrt zu
    Englisch.

    Returns:
        "de" fuer eine deutschsprachige Umgebung, sonst immer "en".
    """
    code = ""
    with contextlib.suppress(Exception):
        code = locale.getlocale()[0] or ""
    if not code:
        with contextlib.suppress(Exception):
            code = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    return "de" if code.lower().startswith("de") else "en"


def load_locale(lang: str) -> None:
    """Laedt eine Sprachdatei (z.B. 'de', 'en').

    Args:
        lang:
        Sprachkuerzel. Unbekannte Werte fallen auf Englisch zurueck.
    """
    global _strings, _current_lang

    if lang not in SUPPORTED_LANGUAGES:
        logger.warning("Sprache '%s' nicht unterstuetzt, verwende '%s'", lang, DEFAULT_LANGUAGE)
        lang = DEFAULT_LANGUAGE

    try:
        locale_file = resources.files("c2pa_scanner") / "locale" / f"{lang}.json"
        _strings = json.loads(locale_file.read_text(encoding="utf-8"))
        _current_lang = lang
    except Exception:
        logger.exception("Fehler beim Laden der Sprachdatei '%s'", lang)
        _strings = {}
        _current_lang = lang


def current_language() -> str:
    """Gibt die aktuell geladene Sprache zurueck."""
    return _current_lang


def t(key: str, **kwargs: object) -> str:
    """Uebersetzt einen Schluessel. Platzhalter via {name} und kwargs.

    Fehlt der Schluessel, wird er selbst zurueckgegeben - so faellt eine
    Luecke in der Oberflaeche auf, statt einen leeren Text zu erzeugen.
    """
    template = _strings.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def format_datetime(timestamp: str, lang: str | None = None) -> str:
    """Formatiert einen ISO-Zeitstempel sprachabhaengig (Datum + Uhrzeit).

    DE: ``dd.MM.yyyy HH:mm``, EN/Fallback: ISO ``yyyy-MM-dd HH:mm``.

    Args:
        timestamp:
        Zeitstempel als ISO-String. Leer oder ungueltig fuehrt zu "?".
        lang:
        Sprachkuerzel. Default: die aktuell geladene Sprache.

    Returns:
        Formatierter Datum/Zeit-String.
    """
    if not timestamp:
        return "?"
    if lang is None:
        lang = _current_lang
    try:
        parsed = datetime.fromisoformat(timestamp)
    except (ValueError, TypeError):
        # Robust gegen schlecht gespeicherte Werte: nehmen was geht.
        return timestamp[:16].replace("T", " ")
    return parsed.strftime("%d.%m.%Y %H:%M" if lang == "de" else "%Y-%m-%d %H:%M")

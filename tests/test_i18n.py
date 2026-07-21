"""Tests fuer die Mehrsprachigkeit.

Der wichtigste Test hier ist test_all_keys_used_in_code_exist: er liest die
tatsaechlich im Quelltext verwendeten Schluessel und prueft sie gegen beide
Sprachdateien. Ohne ihn faellt ein Tippfehler erst auf, wenn der Schluessel
selbst in der Oberflaeche steht.
"""

from __future__ import annotations

import json
import locale
import re
from pathlib import Path

from c2pa_scanner.i18n import (
    SUPPORTED_LANGUAGES,
    current_language,
    detect_language,
    load_locale,
    t,
)

_SRC = Path(__file__).resolve().parent.parent / "src" / "c2pa_scanner"
_LOCALE = _SRC / "locale"


def _keys(lang: str) -> dict[str, str]:
    return json.loads((_LOCALE / f"{lang}.json").read_text(encoding="utf-8"))


class TestLocaleFiles:
    def test_all_supported_languages_have_a_file(self) -> None:
        for lang in SUPPORTED_LANGUAGES:
            assert (_LOCALE / f"{lang}.json").is_file()

    def test_both_files_have_the_same_keys(self) -> None:
        assert set(_keys("de")) == set(_keys("en"))

    def test_no_empty_values(self) -> None:
        for lang in SUPPORTED_LANGUAGES:
            empty = [k for k, v in _keys(lang).items() if not v.strip()]
            assert not empty, f"{lang}: leere Texte bei {empty}"

    def test_placeholders_match_between_languages(self) -> None:
        """Ein Platzhalter, den nur eine Sprache kennt, bricht dort die Ausgabe."""
        de, en = _keys("de"), _keys("en")
        for key in de:
            assert set(re.findall(r"{(\w+)}", de[key])) == set(
                re.findall(r"{(\w+)}", en[key])
            ), f"Platzhalter weichen ab: {key}"

    def test_all_keys_used_in_code_exist(self) -> None:
        used: set[str] = set()
        for path in _SRC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            # Negativer Lookbehind: .get("x") und format("x") enden ebenfalls
            # auf "t(" und sind keine Uebersetzungsaufrufe.
            used.update(re.findall(r'(?<![A-Za-z_.])t\(\s*"([a-z][a-z0-9_.]*\.[a-z0-9_.]+)"', text))
            # Schluessel, die ueber eine Zuordnung laufen (Verdicts, Reglerstufen)
            used.update(re.findall(r'"((?:verdict|settings\.rate_step|binding)\.[a-z_]+)"', text))
        known = set(_keys("de"))
        missing = sorted(k for k in used if k not in known)
        assert not missing, f"Im Code verwendet, aber nicht uebersetzt: {missing}"

    def test_no_obviously_unused_keys(self) -> None:
        """Meldet Schluessel, die nirgends im Quelltext auftauchen."""
        blob = "\n".join(p.read_text(encoding="utf-8") for p in _SRC.rglob("*.py"))
        stale = [k for k in _keys("de") if k not in blob and f"{k}_tip" not in blob]
        # Tooltips werden aus dem Basisschluessel zusammengesetzt (binding.x_tip).
        stale = [k for k in stale if not k.endswith("_tip")]
        assert not stale, f"Nicht verwendete Schluessel: {stale}"


class TestTranslation:
    def test_german_text(self) -> None:
        load_locale("de")
        assert t("common.close") == "Schließen"

    def test_english_text(self) -> None:
        load_locale("en")
        assert t("common.close") == "Close"

    def test_placeholder_substitution(self) -> None:
        load_locale("de")
        assert "42" in t("table.count_all", total=42)

    def test_unknown_key_returns_itself(self) -> None:
        load_locale("de")
        assert t("gibt.es.nicht") == "gibt.es.nicht"

    def test_unknown_language_falls_back_to_english(self) -> None:
        load_locale("xx")
        assert current_language() == "en"
        assert t("common.close") == "Close"


class TestLanguageDetection:
    def test_german_environment(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(locale, "getlocale", lambda *a: ("de_DE", "UTF-8"))
        assert detect_language() == "de"

    def test_english_environment(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(locale, "getlocale", lambda *a: ("en_GB", "UTF-8"))
        assert detect_language() == "en"

    def test_other_language_falls_back_to_english(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(locale, "getlocale", lambda *a: ("fr_FR", "UTF-8"))
        assert detect_language() == "en"

    def test_broken_locale_falls_back_to_english(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        def boom(*args: object) -> tuple[str, str]:
            raise ValueError("unknown locale")

        monkeypatch.setattr(locale, "getlocale", boom)
        monkeypatch.delenv("LC_ALL", raising=False)
        monkeypatch.delenv("LANG", raising=False)
        assert detect_language() == "en"

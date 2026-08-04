"""CLI-Einstieg fuer c2pa-scanner. Absolute Imports (Nuitka/PyInstaller-Regel)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TextIO

# PLAYWRIGHT_BROWSERS_PATH muss gesetzt sein, BEVOR playwright importiert wird,
# damit das gebundelte Chromium im "browsers"-Unterordner gefunden wird.
# PyInstaller setzt sys.frozen, Nuitka stattdessen __compiled__.
_is_frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()
if _is_frozen:
    _browsers_dir = os.path.join(os.path.dirname(sys.executable), "browsers")
    if os.path.isdir(_browsers_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers_dir

from c2pa_scanner import __author__, __version__  # noqa: E402 - nach dem Browsers-Path-Setup
from c2pa_scanner.domain.models import ImageFinding, Verdict  # noqa: E402

# Log-Handle offen halten, solange der Prozess laeuft - faulthandler schreibt
# beim fatalen Signal direkt hinein. Ohne Referenz wuerde der GC es schliessen.
_fault_log: TextIO | None = None

_VERDICT_LABEL = {
    Verdict.AI_GENERATED: "KI-GENERIERT",
    Verdict.AI_EDITED: "KI-BEARBEITET",
    Verdict.C2PA_OTHER: "C2PA (kein KI)",
    Verdict.NO_C2PA: "kein C2PA",
    Verdict.ERROR: "FEHLER",
}


def _short_source_type(dst: str | None) -> str:
    """Kuerzt die digitalSourceType-URI auf das letzte Segment."""
    if not dst:
        return "-"
    return dst.rstrip("/").rsplit("/", 1)[-1]


def _print_findings(findings: list[ImageFinding], pages: int) -> None:
    print(f"{'Verdict':<14} {'digitalSourceType':<40} Bild")
    print("-" * 100)
    for f in findings:
        label = _VERDICT_LABEL.get(f.verdict, f.verdict.value)
        print(f"{label:<14} {_short_source_type(f.digital_source_type):<40} {f.image_url}")
    total = len(findings)
    needs = sum(1 for f in findings if f.verdict.needs_label)
    errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
    print("-" * 100)
    print(f"Seiten: {pages}   Bilder: {total}   KI (Label noetig): {needs}   Fehler: {errors}")


def _cmd_selftest(_args: argparse.Namespace) -> int:
    """Prueft, ob die native C2PA-Bibliothek in diesem Build geladen werden kann."""
    from c2pa_scanner.infrastructure.c2pa_reader import (
        C2paUnavailableError,
        ensure_c2pa_available,
    )

    try:
        ensure_c2pa_available()
    except C2paUnavailableError as exc:
        print(f"FEHLER: C2PA-Bibliothek nicht ladbar: {exc}", file=sys.stderr)
        return 1
    import c2pa

    print(f"OK: C2PA-Bibliothek geladen (c2pa-python {getattr(c2pa, '__version__', '?')})")
    return 0


def _disclaimer_ok(accepted_flag: bool) -> bool:
    """Prueft die Zustimmung zum Haftungshinweis fuer den Kommandozeilenbetrieb.

    Liegt keine Zustimmung zur aktuellen Fassung vor, wird der Wortlaut ausgegeben
    und abgebrochen - bestaetigt wird ausschliesslich ueber --accept-disclaimer,
    damit die Zustimmung eine bewusste Handlung bleibt.

    Args:
        accepted_flag:
        Wert von --accept-disclaimer.

    Returns:
        True, wenn der Lauf starten darf.
    """
    from textual_widgets import DISCLAIMER_VERSION, DisclaimerStore, disclaimer_text

    from c2pa_scanner.i18n import current_language
    from c2pa_scanner.infrastructure.settings import JsonSettingsStore

    store = DisclaimerStore(JsonSettingsStore().path.parent / "disclaimer.json")
    if store.accepted_version == DISCLAIMER_VERSION:
        return True
    if not accepted_flag:
        print(disclaimer_text(current_language(), author=__author__), file=sys.stderr)
        print(
            "\nDieser Hinweis ist zu bestaetigen, bevor ein Scan startet:\n"
            "  c2pa-scanner scan <sitemap> --accept-disclaimer",
            file=sys.stderr,
        )
        return False
    store.record()
    return True


def _cmd_scan(args: argparse.Namespace) -> int:
    import asyncio

    from c2pa_scanner.infrastructure.c2pa_reader import (
        C2paUnavailableError,
        ensure_c2pa_available,
    )
    from c2pa_scanner.services.sitemap_scan import SitemapScanService

    if not _disclaimer_ok(args.accept_disclaimer):
        return 2

    # Ohne die native Bibliothek waere jedes Bild still "kein C2PA" - hart abbrechen.
    try:
        ensure_c2pa_available()
    except C2paUnavailableError as exc:
        print(f"C2PA-Bibliothek nicht ladbar: {exc}", file=sys.stderr)
        return 1

    findings: list[ImageFinding] = []
    pages = {"n": 0}
    try:
        asyncio.run(
            SitemapScanService(rate_per_minute=args.rate_limit).scan(
                args.sitemap,
                on_pages=lambda n: pages.__setitem__("n", n),
                on_finding=findings.append,
                on_log=lambda m: print(m, file=sys.stderr),
                render=args.render,
                respect_robots=not args.ignore_robots,
                accept_consent=not args.no_consent,
            )
        )
    except Exception as exc:  # noqa: BLE001 - Fehler dem User zeigen
        print(f"Scan fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    findings.sort(key=lambda f: (0 if f.verdict.needs_label else 1, f.image_url))
    _print_findings(findings, pages["n"])
    return 0


def _cmd_make_testimage(args: argparse.Namespace) -> int:
    from c2pa_scanner.infrastructure.c2pa_signer import (
        COMPOSITE_WITH_TRAINED,
        TRAINED_ALGORITHMIC_MEDIA,
        create_test_image,
    )

    source_type = COMPOSITE_WITH_TRAINED if args.edited else TRAINED_ALGORITHMIC_MEDIA
    dest = create_test_image(Path(args.out), source_type=source_type)
    print(f"Testbild geschrieben: {dest}")
    print(f"digitalSourceType: {source_type}")
    return 0


def _terminal_supports_graphics() -> bool:
    import os

    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if os.environ.get("KITTY_WINDOW_ID") or "kitty" in term or "ghostty" in term:
        return True
    if term_program in ("wezterm", "ghostty", "mintty", "iterm.app"):
        return True
    if os.environ.get("KONSOLE_VERSION") or os.environ.get("WT_SESSION"):
        return True
    return term in ("foot", "xterm", "mlterm", "mintty")


def _preinit_graphics() -> None:
    """textual-image vor App-Start eager importieren, sonst leaken DA1-Antworten in stdin."""
    import contextlib
    import time

    if not _terminal_supports_graphics():
        return
    with contextlib.suppress(Exception):
        import textual_image.renderable  # noqa: F401
        import textual_image.widget  # noqa: F401
        from textual_image._terminal import get_cell_size

        get_cell_size()
        time.sleep(0.15)


def _run_tui(sitemap: str | None) -> int:
    from c2pa_scanner.infrastructure.settings import JsonSettingsStore

    # Grafik-Pre-Init nur, wenn die grafische Vorschau (Sixel/TGP) aktiviert ist -
    # sonst gar kein textual-image-Import (vermeidet DA-Query/Rendering-Risiken).
    if bool(JsonSettingsStore().load().get("graphics_preview", False)):
        _preinit_graphics()

    from textual_widgets import reset_terminal_title, set_terminal_title

    from c2pa_scanner.app import C2paScannerApp

    set_terminal_title(f"c2pa-scanner v{__version__}")
    try:
        C2paScannerApp(start_sitemap=sitemap).run()
    finally:
        reset_terminal_title()
        _reset_mouse_tracking()
    return 0


def _enable_faulthandler() -> None:
    """Faengt HARTE Abstuerze ab, die an Pythons Exception-Handling UND am
    finally-Block vorbeilaufen: native Access Violation, Stack-Overflow, fataler
    Interpreter-Fehler.

    faulthandler installiert einen Handler fuer fatale Signale (unter Windows
    auch fuer Access Violations) und schreibt beim Absturz den Traceback aller
    Threads in fault.log - separat vom Terminal, das der Maus-Tracking-Muell
    sonst unlesbar macht. Der CrashGuard und _persist_crash greifen nur bei
    normalen Python-Exceptions, dieser Handler bei allem darunter.

    Die Startzeile ist die zweite Haelfte der Diagnose: steht danach nichts
    weiter in der Datei, wurde der Prozess von aussen abgeraeumt, statt an einem
    Fehler zu sterben, den Python haette sehen koennen.
    """
    import atexit
    import contextlib
    import faulthandler
    from datetime import datetime

    from c2pa_scanner.infrastructure.settings import JsonSettingsStore

    global _fault_log
    with contextlib.suppress(Exception):
        verzeichnis = JsonSettingsStore().path.parent
        verzeichnis.mkdir(parents=True, exist_ok=True)
        # Bewusst offen lassen (Prozess-Lebensdauer) - faulthandler schreibt
        # beim fatalen Signal direkt in dieses Handle.
        _fault_log = open(verzeichnis / "fault.log", "a", encoding="utf-8")  # noqa: SIM115
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005 - lokale Zeit
        _fault_log.write(f"\n===== Start {stamp} - v{__version__} =====\n")
        _fault_log.flush()
        faulthandler.enable(file=_fault_log, all_threads=True)
        # Gegenstueck zur Startzeile - siehe _write_fault_end.
        atexit.register(_write_fault_end)


def _reset_mouse_tracking() -> None:
    """Schaltet alle Maus-Tracking-Modi des Terminals ab (idempotent).

    ?1000/?1002/?1003 = Tracking-Modi, ?1006/?1015 = erweitertes Encoding.
    Sind sie bereits aus, bewirken die Sequenzen nichts.

    Schreibt bewusst nach sys.__stdout__, NICHT sys.stdout: Textual kapert
    sys.stdout zur Laufzeit, ein Reset dorthin landet im Nichts und das Terminal
    bleibt im Maus-Tracking-Modus haengen. sys.__stdout__ ist die echte Konsole.
    Der garantierte Reset passiert ohnehin im Shell-Wrapper run.ps1 (laeuft auch
    nach einem harten Crash) - das hier ist der zusaetzliche In-Prozess-Pfad.
    """
    stream = sys.__stdout__
    if stream is None or not stream.isatty():
        return
    stream.write("\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1015l")
    stream.flush()


def _cmd_tui(args: argparse.Namespace) -> int:
    return _run_tui(args.sitemap)


def build_parser() -> argparse.ArgumentParser:
    """Baut die Kommandozeilen-Schnittstelle auf (getrennt von main, damit die
    Vorgabewerte testbar bleiben)."""
    parser = argparse.ArgumentParser(
        prog="c2pa-scanner",
        description=(
            "Erkennt C2PA-/KI-Herkunft in Bildern (EU AI Act Art. 50)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"c2pa-scanner {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    p_tui = sub.add_parser("tui", help="Grafische TUI starten (Standard ohne Befehl)")
    p_tui.add_argument("sitemap", nargs="?", help="Optionale Start-Sitemap (URL oder .xml)")
    p_tui.set_defaults(func=_cmd_tui)

    p_scan = sub.add_parser("scan", help="Sitemap crawlen und Bilder auf C2PA/KI pruefen")
    p_scan.add_argument("sitemap", help="Sitemap-URL oder lokale sitemap.xml")
    p_scan.add_argument(
        "--render",
        action="store_true",
        help="Seiten mit Playwright rendern (findet auch JS-/Shadow-DOM-Bilder, langsamer)",
    )
    p_scan.add_argument(
        "--no-consent",
        action="store_true",
        help=(
            "Cookie-Banner NICHT automatisch akzeptieren (wirkt nur mit --render; "
            "ohne Zustimmung bleiben Bilder ungeladen, die eine Seite erst danach freigibt)"
        ),
    )
    p_scan.add_argument(
        "--ignore-robots",
        action="store_true",
        help="robots.txt ignorieren (nur fuer eigene Seiten sinnvoll)",
    )
    p_scan.add_argument(
        "--rate-limit",
        type=int,
        default=60,
        metavar="N",
        help=(
            "Hoechstens N Requests pro Minute (Seiten, Renderings und Bilder zusammen). "
            "Standard: 60. Mit 0 laeuft der Scan ungebremst - das kann ein "
            "Produktivsystem spuerbar belasten"
        ),
    )
    p_scan.add_argument(
        "--accept-disclaimer",
        action="store_true",
        help=(
            "Haftungs- und Nutzungshinweis bestaetigen (einmalig noetig; ohne "
            "Bestaetigung wird der Hinweis ausgegeben und abgebrochen)"
        ),
    )
    p_scan.set_defaults(func=_cmd_scan)

    p_make = sub.add_parser("make-testimage", help="Signiertes C2PA-Testbild erzeugen")
    p_make.add_argument("out", help="Zieldatei (.jpg)")
    p_make.add_argument(
        "--edited",
        action="store_true",
        help="compositeWithTrainedAlgorithmicMedia statt trainedAlgorithmicMedia",
    )
    p_make.set_defaults(func=_cmd_make_testimage)

    p_self = sub.add_parser(
        "selftest", help="Prueft, ob die native C2PA-Bibliothek geladen werden kann"
    )
    p_self.set_defaults(func=_cmd_selftest)

    return parser


def _init_language() -> None:
    """Laedt die Oberflaechensprache: gespeicherte Wahl, sonst Systemumgebung."""
    from c2pa_scanner.i18n import detect_language, load_locale
    from c2pa_scanner.infrastructure.settings import JsonSettingsStore

    stored = JsonSettingsStore().load().get("language")
    load_locale(stored if isinstance(stored, str) and stored else detect_language())


def main() -> int:
    """Wertet die Kommandozeile aus und startet den gewaehlten Befehl."""
    _enable_faulthandler()
    _init_language()
    args = build_parser().parse_args()
    if args.command is None:
        return _run_tui(None)
    result: int = args.func(args)
    return result


def _write_fault_end() -> None:
    """Schreibt die Endzeile der Sitzungsklammer (ueber atexit registriert).

    Erst dieses Gegenstueck zur Startzeile macht die Datei aussagekraeftig:

      Start + Ende            -> sauber beendet
      Start + Traceback       -> Python-Fehler (der Handler hat ihn gesehen)
      Start und sonst nichts  -> Prozess hart abgeraeumt

    Unter Windows hilft ein Signalhandler dabei nicht: ein Abbruch von aussen
    laeuft dort ueber TerminateProcess und liefert dem Ziel kein abfangbares
    Signal. Die FEHLENDE Endzeile ist der einzige Beleg.
    """
    import contextlib
    from datetime import datetime

    if _fault_log is None:
        return
    with contextlib.suppress(Exception):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _fault_log.write(f"===== Ende {stamp} =====\n")
        _fault_log.flush()


if __name__ == "__main__":
    sys.exit(main())

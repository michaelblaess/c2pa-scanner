"""CLI-Einstieg fuer c2pa-scanner. Absolute Imports (Nuitka/PyInstaller-Regel)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from c2pa_scanner import __version__
from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.infrastructure.c2pa_reader import C2paLibReader
from c2pa_scanner.infrastructure.image_source import iter_images
from c2pa_scanner.services.scan_service import ScanService

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


def _print_table(findings: list[ImageFinding]) -> None:
    print(f"{'Verdict':<14} {'digitalSourceType':<40} Datei")
    print("-" * 100)
    for f in findings:
        label = _VERDICT_LABEL.get(f.verdict, f.verdict.value)
        print(f"{label:<14} {_short_source_type(f.digital_source_type):<40} {f.source}")


def _print_summary(findings: list[ImageFinding]) -> None:
    total = len(findings)
    needs_label = sum(1 for f in findings if f.verdict.needs_label)
    errors = sum(1 for f in findings if f.verdict is Verdict.ERROR)
    print("-" * 100)
    print(f"Gesamt: {total}   KI (Label noetig): {needs_label}   Fehler: {errors}")


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.exists():
        print(f"Pfad nicht gefunden: {root}", file=sys.stderr)
        return 2
    images = iter_images(root, recursive=not args.no_recursive)
    if not images:
        print("Keine Bilder gefunden.")
        return 0
    findings = ScanService(C2paLibReader()).scan_paths(images)
    _print_table(findings)
    _print_summary(findings)
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


def _run_tui(folder: str | None) -> int:
    _preinit_graphics()
    from textual_widgets import reset_terminal_title, set_terminal_title

    from c2pa_scanner.app import C2paScannerApp

    set_terminal_title(f"c2pa-scanner v{__version__}")
    try:
        C2paScannerApp(Path(folder) if folder else None).run()
    finally:
        reset_terminal_title()
    return 0


def _cmd_tui(args: argparse.Namespace) -> int:
    return _run_tui(args.folder)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="c2pa-scanner",
        description=(
            "Selbstpruef-Werkzeug: erkennt C2PA-/KI-Herkunft in Bildern (EU AI Act Art. 50)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"c2pa-scanner {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    p_tui = sub.add_parser("tui", help="Grafische TUI starten (Standard ohne Befehl)")
    p_tui.add_argument("folder", nargs="?", help="Optionaler Startordner")
    p_tui.set_defaults(func=_cmd_tui)

    p_scan = sub.add_parser("scan", help="Verzeichnis/Datei nach C2PA-Herkunft pruefen")
    p_scan.add_argument("path", help="Verzeichnis oder einzelne Bilddatei")
    p_scan.add_argument(
        "--no-recursive", action="store_true", help="Unterverzeichnisse nicht durchsuchen"
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

    args = parser.parse_args()
    if args.command is None:
        return _run_tui(None)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())

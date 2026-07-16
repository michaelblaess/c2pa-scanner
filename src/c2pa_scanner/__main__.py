"""CLI-Einstieg fuer c2pa-scanner. Absolute Imports (Nuitka/PyInstaller-Regel)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from c2pa_scanner import __version__
from c2pa_scanner.domain.models import ImageFinding, Verdict

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


def _cmd_scan(args: argparse.Namespace) -> int:
    import asyncio

    from c2pa_scanner.services.sitemap_scan import SitemapScanService

    findings: list[ImageFinding] = []
    pages = {"n": 0}
    try:
        asyncio.run(
            SitemapScanService().scan(
                args.sitemap,
                on_pages=lambda n: pages.__setitem__("n", n),
                on_finding=findings.append,
                on_log=lambda m: print(m, file=sys.stderr),
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
    return 0


def _cmd_tui(args: argparse.Namespace) -> int:
    return _run_tui(args.sitemap)


def main() -> int:
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

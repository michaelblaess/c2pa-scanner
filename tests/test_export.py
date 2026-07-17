"""Tests fuer den Findings-Export (JSON / JIRA-Markdown / JIRA-Wiki / Text)."""

from __future__ import annotations

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.services.export import build_jira


def _finding(**kwargs: object) -> ImageFinding:
    base: dict[str, object] = {
        "image_url": "https://example.com/img.jpg",
        "page_url": "https://example.com/seite",
        "has_c2pa": True,
        "digital_source_type": "trainedAlgorithmicMedia",
        "verdict": Verdict.AI_GENERATED,
        "width": 1200,
        "height": 800,
    }
    base.update(kwargs)
    return ImageFinding(**base)  # type: ignore[arg-type]


def test_markdown_is_default_with_separator_row() -> None:
    out = build_jira([_finding()]).splitlines()
    assert out[0] == "| Status | Herkunft | Bild | Größe | Seite |"
    assert out[1] == "| --- | --- | --- | --- | --- |"
    assert out[2].startswith("| KI-generiert | trainedAlgorithmicMedia |")
    assert out[2].endswith("| 1200x800 | https://example.com/seite |")


def test_markdown_escapes_pipe_and_newline_in_cells() -> None:
    finding = _finding(
        verdict=Verdict.ERROR,
        error="Timeout | Zeile1\nZeile2",
        digital_source_type=None,
    )
    row = build_jira([finding]).splitlines()[2]
    assert "Timeout \\| Zeile1<br>Zeile2" in row
    # keine rohen Zeilenumbrueche, die die Tabelle brechen wuerden
    assert "\n" not in row


def test_wiki_format_uses_double_pipe_header() -> None:
    out = build_jira([_finding()], fmt="wiki").splitlines()
    assert out[0] == "||Status||Herkunft||Bild||Größe||Seite||"
    assert out[1].startswith("|KI-generiert|trainedAlgorithmicMedia|")


def test_fmt_is_case_insensitive() -> None:
    assert build_jira([_finding()], fmt="WIKI").startswith("||Status||")
    assert build_jira([_finding()], fmt="Markdown").startswith("| Status |")

"""Export der Findings als JSON, JIRA-Tabelle oder Klartext."""

from __future__ import annotations

import json
from collections.abc import Sequence

from c2pa_scanner.domain.models import ImageFinding, Verdict
from c2pa_scanner.i18n import t

_STATUS: dict[Verdict, str] = {
    Verdict.AI_GENERATED: "verdict.ai_generated",
    Verdict.AI_EDITED: "verdict.ai_edited",
    Verdict.C2PA_OTHER: "verdict.c2pa_other",
    Verdict.NO_C2PA: "verdict.no_c2pa",
    Verdict.ERROR: "verdict.error",
}


def _herkunft(finding: ImageFinding) -> str:
    if finding.verdict is Verdict.ERROR and finding.error:
        return finding.error
    return finding.digital_source_type or finding.generator or ""


def _size(finding: ImageFinding) -> str:
    return f"{finding.width}x{finding.height}" if finding.width and finding.height else ""


def build_json(findings: Sequence[ImageFinding]) -> str:
    data = [
        {
            "status": t(_STATUS[f.verdict]),
            "verdict": f.verdict.value,
            "image_url": f.image_url,
            "page_url": f.page_url,
            "digital_source_type": f.digital_source_type,
            "generator": f.generator,
            "width": f.width,
            "height": f.height,
            "error": f.error,
        }
        for f in findings
    ]
    return json.dumps(data, indent=2, ensure_ascii=False)


def _md_cell(text: str) -> str:
    # Pipe kollidiert mit dem Markdown-Zellseparator, Zeilenumbruch bricht die Zeile
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _build_jira_markdown(findings: Sequence[ImageFinding]) -> str:
    lines = [
        (
            f"| {t('table.status')} | {t('table.origin')} | {t('table.image')} "
            f"| {t('table.size')} | {t('table.page')} |"
        ),
        "| --- | --- | --- | --- | --- |",
    ]
    for f in findings:
        cells = [
            t(_STATUS[f.verdict]),
            _herkunft(f) or "-",
            f.image_url,
            _size(f) or "-",
            f.page_url,
        ]
        lines.append(f"| {' | '.join(_md_cell(c) for c in cells)} |")
    return "\n".join(lines)


def _build_jira_wiki(findings: Sequence[ImageFinding]) -> str:
    lines = [
        f"||{t('table.status')}||{t('table.origin')}||{t('table.image')}"
        f"||{t('table.size')}||{t('table.page')}||"
    ]
    for f in findings:
        lines.append(
            f"|{t(_STATUS[f.verdict])}|{_herkunft(f) or '-'}|{f.image_url}"
            f"|{_size(f) or '-'}|{f.page_url}|"
        )
    return "\n".join(lines)


def build_jira(findings: Sequence[ImageFinding], fmt: str = "markdown") -> str:
    """Baut die JIRA-Tabelle.

    fmt='markdown' erzeugt eine GitHub-Flavored-Markdown-Tabelle fuer Jira Cloud
    (wird beim Einfuegen automatisch in eine ADF-Tabelle konvertiert - das alte
    Wiki Markup versteht der Cloud-Editor nicht mehr). fmt='wiki' erzeugt das
    klassische Wiki Markup fuer Jira Server/DC.
    """
    return _build_jira_wiki(findings) if fmt.lower() == "wiki" else _build_jira_markdown(findings)


def build_text(findings: Sequence[ImageFinding]) -> str:
    header = "\t".join(
        (t("table.status"), t("table.origin"), t("table.image"), t("table.size"), t("table.page"))
    )
    lines = [header]
    for f in findings:
        lines.append(
            f"{t(_STATUS[f.verdict])}\t{_herkunft(f)}\t{f.image_url}\t{_size(f)}\t{f.page_url}"
        )
    return "\n".join(lines)

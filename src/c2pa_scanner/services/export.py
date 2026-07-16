"""Export der Findings als JSON, JIRA-Tabelle oder Klartext."""

from __future__ import annotations

import json
from collections.abc import Sequence

from c2pa_scanner.domain.models import ImageFinding, Verdict

_STATUS: dict[Verdict, str] = {
    Verdict.AI_GENERATED: "KI-generiert",
    Verdict.AI_EDITED: "KI-bearbeitet",
    Verdict.C2PA_OTHER: "C2PA (kein KI)",
    Verdict.NO_C2PA: "kein C2PA",
    Verdict.ERROR: "Fehler",
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
            "status": _STATUS[f.verdict],
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


def build_jira(findings: Sequence[ImageFinding]) -> str:
    lines = ["||Status||Herkunft||Bild||Größe||Seite||"]
    for f in findings:
        lines.append(
            f"|{_STATUS[f.verdict]}|{_herkunft(f) or '-'}|{f.image_url}"
            f"|{_size(f) or '-'}|{f.page_url}|"
        )
    return "\n".join(lines)


def build_text(findings: Sequence[ImageFinding]) -> str:
    lines = ["Status\tHerkunft\tBild\tGröße\tSeite"]
    for f in findings:
        lines.append(
            f"{_STATUS[f.verdict]}\t{_herkunft(f)}\t{f.image_url}\t{_size(f)}\t{f.page_url}"
        )
    return "\n".join(lines)

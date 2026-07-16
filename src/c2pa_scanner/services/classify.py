"""Klassifikation: digitalSourceType -> Verdict."""

from __future__ import annotations

from c2pa_scanner.domain.models import Verdict

# IPTC digitalSourceType-Marker (case-insensitiv gesucht).
_AI_EDITED = "compositewithtrainedalgorithmicmedia"
_AI_GENERATED = "trainedalgorithmicmedia"


def classify(digital_source_type: str | None, has_c2pa: bool) -> Verdict:
    """Leitet aus dem digitalSourceType ein Verdict ab.

    Nur die 'trained algorithmic'-Typen gelten als KI (Label-pflichtig). Ein
    vorhandenes Manifest ohne solchen Typ ist reine Herkunft (z.B. Kamera).
    """
    if not has_c2pa:
        return Verdict.NO_C2PA
    if digital_source_type is None:
        return Verdict.C2PA_OTHER
    dst = digital_source_type.lower()
    if _AI_EDITED in dst:
        return Verdict.AI_EDITED
    if _AI_GENERATED in dst:
        return Verdict.AI_GENERATED
    return Verdict.C2PA_OTHER

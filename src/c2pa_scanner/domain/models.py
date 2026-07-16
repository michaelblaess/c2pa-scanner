"""Domain-Modelle: Verdict und ImageFinding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Verdict(Enum):
    """Bewertung eines Bildes anhand seines C2PA-Herkunftsnachweises."""

    AI_GENERATED = "ai-generated"
    AI_EDITED = "ai-edited"
    C2PA_OTHER = "c2pa-other"
    NO_C2PA = "no-c2pa"
    ERROR = "error"

    @property
    def needs_label(self) -> bool:
        """True, wenn dieses Bild nach dem AI-Act ein sichtbares KI-Label braucht."""
        return self in (Verdict.AI_GENERATED, Verdict.AI_EDITED)


@dataclass(frozen=True)
class ImageFinding:
    """Ergebnis der C2PA-Pruefung eines einzelnen Bildes aus einer Seite."""

    image_url: str
    page_url: str
    has_c2pa: bool
    digital_source_type: str | None
    verdict: Verdict
    error: str | None = None
    width: int = 0
    height: int = 0
    generator: str | None = None

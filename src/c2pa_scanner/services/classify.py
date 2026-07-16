"""Klassifikation: digitalSourceType (+ Generator-Tool) -> Verdict."""

from __future__ import annotations

from c2pa_scanner.domain.models import Verdict

# IPTC digitalSourceType-Marker (case-insensitiv gesucht).
_AI_EDITED = "compositewithtrainedalgorithmicmedia"
_AI_GENERATED = "trainedalgorithmicmedia"

# Eindeutige Generativ-KI-Tools (Substring, case-insensitiv). BEWUSST konservativ:
# nur Namen, die praktisch nur bei generativer KI auftauchen. Mehrdeutige Tools
# wie "Adobe Photoshop", "Lightroom" oder "GIMP" gehoeren NICHT hierher - die
# werden auch fuer normale Bearbeitung genutzt und wuerden Falsch-Positive
# erzeugen. Fundstelle ist EXIF `Software` oder XMP `CreatorTool`.
_AI_GENERATOR_MARKERS = (
    "midjourney",
    "dall-e",
    "dall·e",
    "dalle",
    "stable diffusion",
    "stablediffusion",
    "adobe firefly",
    "firefly",
    "google imagen",
    "leonardo.ai",
    "leonardo ai",
    "ideogram",
    "nightcafe",
    "playground ai",
    "dream by wombo",
    "starryai",
)


def _is_ai_generator(generator: str | None) -> bool:
    """Prueft, ob der Tool-/Generator-Name ein eindeutiges Generativ-KI-Tool ist."""
    if not generator:
        return False
    name = generator.lower()
    return any(marker in name for marker in _AI_GENERATOR_MARKERS)


def classify(
    digital_source_type: str | None, has_c2pa: bool, generator: str | None = None
) -> Verdict:
    """Leitet aus digitalSourceType (und ersatzweise dem Generator-Tool) ein Verdict ab.

    Vorrang hat der IPTC-`digitalSourceType`: nur die 'trained algorithmic'-Typen
    gelten als KI. Der Marker zaehlt auch aus dem XMP (ohne gueltiges C2PA) - so
    werden Bilder erkannt, die ihre Signatur beim Resize verloren, aber das XMP
    behalten haben. Fehlt jeder KI-Marker, greift ersatzweise der Tool-Name aus
    EXIF/XMP: ein eindeutiges Generativ-KI-Tool (z.B. Midjourney) gilt als KI.
    """
    if digital_source_type is not None:
        # Ein expliziter (signierter/eingebetteter) Typ ist autoritativ und wird
        # NICHT durch einen Tool-Namen ueberstimmt.
        dst = digital_source_type.lower()
        if _AI_EDITED in dst:
            return Verdict.AI_EDITED
        if _AI_GENERATED in dst:
            return Verdict.AI_GENERATED
        return Verdict.C2PA_OTHER

    # Kein digitalSourceType -> ersatzweise das erzeugende Tool aus EXIF/XMP.
    if _is_ai_generator(generator):
        return Verdict.AI_GENERATED

    return Verdict.C2PA_OTHER if has_c2pa else Verdict.NO_C2PA

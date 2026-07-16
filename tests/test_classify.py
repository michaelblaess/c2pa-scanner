"""Tests fuer die digitalSourceType-Klassifikation."""

from __future__ import annotations

from c2pa_scanner.domain.models import Verdict
from c2pa_scanner.services.classify import classify

_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"


class TestClassify:
    def test_no_manifest_is_no_c2pa(self) -> None:
        assert classify(None, has_c2pa=False) is Verdict.NO_C2PA

    def test_manifest_without_source_type_is_other(self) -> None:
        assert classify(None, has_c2pa=True) is Verdict.C2PA_OTHER

    def test_trained_algorithmic_media_is_ai_generated(self) -> None:
        assert classify(_BASE + "trainedAlgorithmicMedia", has_c2pa=True) is Verdict.AI_GENERATED

    def test_composite_is_ai_edited(self) -> None:
        dst = _BASE + "compositeWithTrainedAlgorithmicMedia"
        assert classify(dst, has_c2pa=True) is Verdict.AI_EDITED

    def test_camera_capture_is_other(self) -> None:
        assert classify(_BASE + "digitalCapture", has_c2pa=True) is Verdict.C2PA_OTHER

    def test_ai_verdicts_need_label(self) -> None:
        assert Verdict.AI_GENERATED.needs_label
        assert Verdict.AI_EDITED.needs_label
        assert not Verdict.C2PA_OTHER.needs_label
        assert not Verdict.NO_C2PA.needs_label

    def test_xmp_source_type_without_c2pa_is_ai(self) -> None:
        # digitalSourceType nur im XMP (kein gueltiges C2PA) zaehlt trotzdem als KI.
        assert (
            classify(_BASE + "trainedAlgorithmicMedia", has_c2pa=False) is Verdict.AI_GENERATED
        )

    def test_known_ai_generator_is_ai(self) -> None:
        # Kein digitalSourceType, aber eindeutiges KI-Tool im Software/CreatorTool-Tag.
        assert classify(None, has_c2pa=False, generator="Midjourney") is Verdict.AI_GENERATED
        assert classify(None, has_c2pa=False, generator="Adobe Firefly") is Verdict.AI_GENERATED

    def test_ambiguous_editor_is_not_ai(self) -> None:
        # Normale Bildbearbeitung darf KEIN Falsch-Positiv erzeugen.
        assert classify(None, has_c2pa=False, generator="Adobe Photoshop 26.0") is Verdict.NO_C2PA
        assert classify(None, has_c2pa=True, generator="GIMP 2.10") is Verdict.C2PA_OTHER

    def test_explicit_source_type_wins_over_generator(self) -> None:
        # Ein nicht-KI digitalSourceType wird nicht durch einen Tool-Namen ueberstimmt.
        assert (
            classify(_BASE + "digitalCapture", has_c2pa=True, generator="Firefly")
            is Verdict.C2PA_OTHER
        )

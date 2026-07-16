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

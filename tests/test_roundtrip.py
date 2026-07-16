"""End-to-End: signiertes Testbild erzeugen und wieder auslesen (echte c2pa-Lib)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from c2pa_scanner.domain.models import Verdict
from c2pa_scanner.infrastructure.c2pa_reader import C2paLibReader
from c2pa_scanner.infrastructure.c2pa_signer import (
    COMPOSITE_WITH_TRAINED,
    TRAINED_ALGORITHMIC_MEDIA,
    create_test_image,
)
from c2pa_scanner.services.classify import classify


class TestRoundtrip:
    def test_generated_image_is_detected_as_ai(self, tmp_path: Path) -> None:
        dest = create_test_image(tmp_path / "ai.jpg", source_type=TRAINED_ALGORITHMIC_MEDIA)
        has_c2pa, dst = C2paLibReader().read(dest)
        assert has_c2pa
        assert dst is not None
        assert "trainedAlgorithmicMedia" in dst
        assert classify(dst, has_c2pa) is Verdict.AI_GENERATED

    def test_edited_image_is_detected_as_ai_edited(self, tmp_path: Path) -> None:
        dest = create_test_image(tmp_path / "edit.jpg", source_type=COMPOSITE_WITH_TRAINED)
        has_c2pa, dst = C2paLibReader().read(dest)
        assert has_c2pa
        assert classify(dst, has_c2pa) is Verdict.AI_EDITED

    def test_plain_image_has_no_manifest(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain.jpg"
        buffer = io.BytesIO()
        Image.new("RGB", (32, 32), (0, 0, 0)).save(buffer, format="JPEG")
        plain.write_bytes(buffer.getvalue())

        has_c2pa, dst = C2paLibReader().read(plain)
        assert not has_c2pa
        assert dst is None
        assert classify(dst, has_c2pa) is Verdict.NO_C2PA

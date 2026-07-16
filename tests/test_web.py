"""Tests fuer Sitemap-Parsing, Bild-Extraktion und C2PA-aus-Bytes."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from c2pa_scanner.infrastructure.c2pa_reader import read_bytes
from c2pa_scanner.infrastructure.c2pa_signer import TRAINED_ALGORITHMIC_MEDIA, create_test_image
from c2pa_scanner.infrastructure.sitemap import parse_sitemap
from c2pa_scanner.infrastructure.web import extract_image_urls_from_html

_NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
_URLSET = f'<urlset {_NS}><url><loc>https://ex.com/a</loc></url><url><loc>https://ex.com/b</loc></url></urlset>'
_INDEX = f'<sitemapindex {_NS}><sitemap><loc>https://ex.com/sm1.xml</loc></sitemap></sitemapindex>'


class TestSitemapParse:
    def test_urlset(self) -> None:
        pages, nested = parse_sitemap(_URLSET)
        assert pages == ["https://ex.com/a", "https://ex.com/b"]
        assert nested == []

    def test_index(self) -> None:
        pages, nested = parse_sitemap(_INDEX)
        assert pages == []
        assert nested == ["https://ex.com/sm1.xml"]


class TestImageExtraction:
    def test_extracts_and_resolves(self) -> None:
        html = (
            '<html><body>'
            '<img src="/img/a.jpg">'
            '<img data-src="b.png">'
            '<img src="data:image/gif;base64,xxx">'
            '<img src="/logo.svg">'
            '<img srcset="/c.webp 1x, /c2.webp 2x">'
            '</body></html>'
        )
        urls = extract_image_urls_from_html(html, "https://ex.com/page/")
        assert "https://ex.com/img/a.jpg" in urls
        assert "https://ex.com/page/b.png" in urls
        assert "https://ex.com/c.webp" in urls
        assert all(not u.startswith("data:") for u in urls)
        assert all(not u.lower().endswith(".svg") for u in urls)  # SVG wird uebersprungen

    def test_finds_urls_in_custom_element_attributes(self) -> None:
        # Bild-URL steckt NICHT in <img src>, sondern in einem Web-Component-Attribut
        # (wie Sitefinity <envc-hero-section image-src=...>); HTML-Entity im Query.
        html = (
            '<envc-hero-section '
            'image-src="/Media/images/hero.jpg?sfvrsn=abc&amp;w=644"></envc-hero-section>'
        )
        urls = extract_image_urls_from_html(html, "https://ex.com/seite")
        assert "https://ex.com/Media/images/hero.jpg?sfvrsn=abc&w=644" in urls


class TestReadBytes:
    def test_detects_ai(self, tmp_path: Path) -> None:
        dest = create_test_image(tmp_path / "ai.jpg", source_type=TRAINED_ALGORITHMIC_MEDIA)
        has_c2pa, dst = read_bytes(dest.read_bytes(), "image/jpeg")
        assert has_c2pa
        assert dst is not None
        assert "trainedAlgorithmicMedia" in dst

    def test_plain_has_none(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain.jpg"
        Image.new("RGB", (16, 16), (0, 0, 0)).save(plain, format="JPEG")
        has_c2pa, dst = read_bytes(plain.read_bytes(), "image/jpeg")
        assert not has_c2pa
        assert dst is None

    def test_sniffs_without_content_type(self, tmp_path: Path) -> None:
        dest = create_test_image(tmp_path / "ai2.jpg", source_type=TRAINED_ALGORITHMIC_MEDIA)
        has_c2pa, dst = read_bytes(dest.read_bytes(), "")
        assert has_c2pa
        assert dst is not None

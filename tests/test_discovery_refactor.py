"""Tests for aggregated discover/search, CSS adapters, resolver, and GenericDetector improvements."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from flask import render_template

import app  # noqa: E402
from services import chapter_parsing, metadata_discovery
from sources.adapters.css_source import CssSourceAdapter
from sources.adapters.mangadex import MangaDexAdapter
from sources.generic_detector import GenericDetector
from sources import resolver as source_resolver


class _Resp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class DiscoveryRefactorTests(unittest.TestCase):
    def test_discover_search_not_only_mangadex_when_second_provider_returns_rows(self) -> None:
        md_row = {
            "source_id": "mangadex",
            "source_name": "MangaDex",
            "external_id": "md-1",
            "title": "Solo Leveling",
            "url": "https://mangadex.org/title/md-1",
            "description": "",
            "cover_url": "https://uploads.mangadex.org/covers/md/c.jpg",
            "latest_chapter": "179",
            "chapter_count": 179,
            "support_level": "official_api",
        }
        other = [
            {
                "source_id": "otherscan",
                "source_name": "OtherScan",
                "external_id": "o1",
                "title": "Different Title",
                "url": "https://reader.example/series/abc",
                "description": "x",
                "cover_url": "",
                "latest_chapter": "10",
                "chapter_count": 10,
                "support_level": "site_adapter",
            }
        ]
        with patch.object(MangaDexAdapter, "search", return_value=[md_row]):
            with patch.object(source_resolver, "search_title", return_value=other):
                out = metadata_discovery.discover_search("Solo Leveling", live=False)
        titles = {r["title"] for r in out["results"]}
        self.assertIn("Solo Leveling", titles)
        self.assertIn("Different Title", titles)
        self.assertFalse(out.get("is_demo"))

    def test_resolve_url_mangakatana_uses_css_adapter_with_mocked_html(self) -> None:
        html = """<!doctype html>
<html><head>
<meta property="og:image" content="https://mangakatana.com/static/cover.jpg"/>
</head><body>
<h1>Katana Series</h1>
<a href="https://mangakatana.com/manga/x/chapter-42">Chapter 42</a>
</body></html>"""
        profile = {
            "id": "mangakatana",
            "display_name": "MangaKatana",
            "domains": ["mangakatana.com"],
            "title_selector": "h1",
            "cover_selector": 'meta[property="og:image"]',
            "chapter_link_selector": "a[href*='chapter']",
            "support_level": "site_adapter",
        }
        adapter = CssSourceAdapter(profile)
        with patch("sources.adapters.css_source.requests.get", return_value=_Resp(html)):
            prev = adapter.resolve_url("https://mangakatana.com/manga/x")
        self.assertEqual(prev.title, "Katana Series")
        self.assertIn("cover.jpg", prev.cover_url or "")
        self.assertTrue(prev.chapters)
        self.assertEqual(prev.latest_chapter, "42")

    def test_generic_detector_og_image_cover(self) -> None:
        html = '<html><head><meta property="og:image" content="https://cdn.example/c.png"/></head><body><h1>T</h1></body></html>'
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        g = GenericDetector()
        url = g.detect_cover(soup, "https://foo.example/manga/x")
        self.assertEqual(url, "https://cdn.example/c.png")

    def test_generic_detector_data_src_cover_absolute(self) -> None:
        html = '<html><body><div class="cover"><img data-src="/img/c.jpg" alt="cover"/></div></body></html>'
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        g = GenericDetector()
        url = g.detect_cover(soup, "https://foo.example/manga/x/")
        self.assertEqual(url, "https://foo.example/img/c.jpg")

    def test_generic_detector_chapter_from_chapter_dash_url(self) -> None:
        html = """<html><body>
<a href="https://foo.example/read/chapter-123">Read</a>
</body></html>"""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        g = GenericDetector()
        ch = g.detect_chapters(soup, "https://foo.example/manga/x")
        self.assertTrue(ch)
        self.assertEqual(ch[0].number, "123")

    def test_parse_chapter_from_url_segment(self) -> None:
        n = chapter_parsing.parse_chapter_from_url("https://ex.com/m/x/chapter-99")
        self.assertEqual(n, 99.0)

    def test_public_search_template_renders_multiple_rows(self) -> None:
        with app.app.test_request_context("/"):
            html = render_template(
                "public_search.html",
                q="test",
                results=[
                    {
                        "title": "A",
                        "slug": "a",
                        "cover_url": "https://ex.com/a.jpg",
                        "source_name": "Src",
                        "best_source": "Src",
                        "support_label": "Supported",
                        "latest_chapter": "5",
                        "source_url": "https://ex.com/m/a",
                        "comparison_slug": "a",
                    },
                    {
                        "title": "B",
                        "slug": "b",
                        "cover_url": "",
                        "source_name": "Src2",
                        "best_source": "Src2",
                        "support_label": "Manual",
                        "latest_chapter": None,
                        "source_url": "https://ex.com/m/b",
                        "comparison_slug": "b",
                    },
                ],
            )
        self.assertIn("A", html)
        self.assertIn("B", html)
        self.assertIn("a.jpg", html)
        self.assertIn("View sources", html)
        with app.app.test_request_context("/"):
            html2 = render_template(
                "public_search.html",
                q="x",
                results=[{"title": "", "slug": "x", "cover_url": "", "source_name": "S"}],
            )
        self.assertIn("Untitled", html2)

    def test_save_discovered_series_defaults_source_name_manual(self) -> None:
        body = metadata_discovery.save_discovered_series(
            {
                "source_url": "https://scan.example/m/x",
                "title": "X",
                "support_level": "site_adapter",
                "detection_source": "backend",
            }
        )
        self.assertEqual(body["source_name"], "Manual")

    def test_css_adapter_403_returns_manual_not_crash(self) -> None:
        profile = {
            "id": "mangakatana",
            "display_name": "MangaKatana",
            "domains": ["mangakatana.com"],
            "title_selector": "h1",
            "cover_selector": ".cover img",
            "chapter_link_selector": "a",
            "support_level": "site_adapter",
        }
        adapter = CssSourceAdapter(profile)
        with patch(
            "sources.adapters.css_source.requests.get",
            return_value=_Resp("", status=403),
        ):
            prev = adapter.resolve_url("https://mangakatana.com/m/x")
        self.assertEqual(prev.support_level, "manual_only")


if __name__ == "__main__":
    unittest.main()

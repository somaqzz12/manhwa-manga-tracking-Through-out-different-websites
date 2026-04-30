"""Tests for MangaDex-backed metadata discovery (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import unittest

from services import metadata_discovery
from sources.adapters.mangadex import MangaDexAdapter


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class MetadataDiscoveryTests(unittest.TestCase):
    def test_mangadex_cover_prefers_relationship_file_name(self) -> None:
        mid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        manga_payload = {
            "data": [
                {
                    "id": mid,
                    "type": "manga",
                    "attributes": {"title": {"en": "Chainsaw Man"}},
                    "relationships": [
                        {"id": cid, "type": "cover_art", "attributes": {"fileName": "from-relationship.jpg"}}
                    ],
                }
            ],
            "included": [
                {"id": cid, "type": "cover_art", "attributes": {"fileName": "from-included.jpg"}},
            ],
        }
        chapter_payload = {"data": [{"id": "ch1", "attributes": {"chapter": "12"}}], "total": 120}

        def fake_get(url: str, *args, **kwargs):
            if "/chapter" in url:
                return _FakeResp(chapter_payload)
            return _FakeResp(manga_payload)

        def session_factory():
            s = MagicMock()
            s.get.side_effect = lambda url, **kw: fake_get(url, **kw)
            return s

        with patch("sources.adapters.mangadex.requests.get", side_effect=fake_get):
            with patch("sources.adapters.mangadex.requests.Session", side_effect=session_factory):
                rows = MangaDexAdapter().search("chainsaw")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["cover_url"].endswith("/from-relationship.jpg"))

    def test_mangadex_search_parses_cover_and_chapter_meta(self) -> None:
        mid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        manga_payload = {
            "data": [
                {
                    "id": mid,
                    "type": "manga",
                    "attributes": {
                        "title": {"en": "Chainsaw Man"},
                        "description": {"en": "Devil hunter."},
                        "status": "ongoing",
                    },
                    "relationships": [{"id": cid, "type": "cover_art"}],
                }
            ],
            "included": [
                {
                    "id": cid,
                    "type": "cover_art",
                    "attributes": {"fileName": "cover.jpg"},
                }
            ],
        }
        chapter_payload = {"data": [{"id": "ch1", "attributes": {"chapter": "12"}}], "total": 120}

        def fake_get(url: str, *args, **kwargs):
            if "/chapter" in url:
                return _FakeResp(chapter_payload)
            return _FakeResp(manga_payload)

        fake_session = MagicMock()

        def session_factory():
            s = MagicMock()
            s.get.side_effect = lambda url, **kw: fake_get(url, **kw)
            return s

        with patch("sources.adapters.mangadex.requests.get", side_effect=fake_get):
            with patch("sources.adapters.mangadex.requests.Session", side_effect=session_factory):
                rows = MangaDexAdapter().search("chainsaw")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["title"], "Chainsaw Man")
        self.assertIn("uploads.mangadex.org/covers", r.get("cover_url", ""))
        self.assertIn(mid, r.get("cover_url", ""))
        self.assertEqual(r.get("latest_chapter"), "12")
        self.assertEqual(r.get("chapter_count"), 120)
        self.assertEqual(r["url"], f"https://mangadex.org/title/{mid}")

    def test_mangadex_search_cover_falls_back_to_included(self) -> None:
        mid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        cid = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        manga_payload = {
            "data": [
                {
                    "id": mid,
                    "type": "manga",
                    "attributes": {"title": {"en": "Chainsaw Man"}},
                    "relationships": [{"id": cid, "type": "cover_art"}],
                }
            ],
            "included": [
                {"id": cid, "type": "cover_art", "attributes": {"fileName": "from-included.jpg"}},
            ],
        }
        chapter_payload = {"data": [{"id": "ch1", "attributes": {"chapter": "12"}}], "total": 120}

        def fake_get(url: str, *args, **kwargs):
            if "/chapter" in url:
                return _FakeResp(chapter_payload)
            return _FakeResp(manga_payload)

        def session_factory():
            s = MagicMock()
            s.get.side_effect = lambda url, **kw: fake_get(url, **kw)
            return s

        with patch("sources.adapters.mangadex.requests.get", side_effect=fake_get):
            with patch("sources.adapters.mangadex.requests.Session", side_effect=session_factory):
                rows = MangaDexAdapter().search("chainsaw")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["cover_url"].endswith("/from-included.jpg"))

    def test_discover_search_formats_api_shape(self) -> None:
        raw = {
            "source_id": "mangadex",
            "source_name": "MangaDex",
            "external_id": "x",
            "title": "T",
            "url": "https://mangadex.org/title/x",
            "description": "D",
            "cover_url": "https://uploads.mangadex.org/covers/x/c.jpg",
            "latest_chapter": "3",
            "chapter_count": 10,
            "support_level": "official_api",
        }
        with patch.object(MangaDexAdapter, "search", return_value=[raw]):
            out = metadata_discovery.discover_search("anything", live=False)
        self.assertTrue(out.get("ok"))
        self.assertFalse(out.get("is_demo"))
        res = out["results"][0]
        self.assertEqual(res["title"], "T")
        self.assertEqual(res["slug"], "x")
        self.assertEqual(res["source_url"], "https://mangadex.org/title/x")
        self.assertEqual(res["support_level"], "official_api")
        self.assertEqual(res["best_source"], "MangaDex")
        self.assertIn("/api/image-proxy?url=", res["cover_url"])

    def test_discover_search_unknown_no_demo_hits_when_mangadex_empty(self) -> None:
        with patch.object(MangaDexAdapter, "search", return_value=[]):
            out = metadata_discovery.discover_search("zzzz-no-catalog-match-xyz", live=False)
        self.assertEqual(out["results"], [])
        self.assertFalse(out["is_demo"])

    def test_save_discovered_series_maps_add_preview(self) -> None:
        body = metadata_discovery.save_discovered_series(
            {
                "source_url": "https://mangadex.org/title/abc",
                "title": "Hi",
                "canonical_title": "Hi",
                "description": "Desc",
                "cover_url": "https://uploads.mangadex.org/covers/a/b.jpg",
                "source_name": "MangaDex",
                "latest_chapter": "9",
                "chapter_count": 10,
                "support_level": "official_api",
                "detection_source": "backend",
            }
        )
        self.assertEqual(body["source_url"], "https://mangadex.org/title/abc")
        self.assertEqual(body["source_domain"], "mangadex.org")
        self.assertEqual(body["latest_chapter"], "9")


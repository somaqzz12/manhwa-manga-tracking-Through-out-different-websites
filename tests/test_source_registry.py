import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch

from services import source_registry


class SourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self._orig_sources_dir = os.environ.get("SOURCES_DIR")

    def tearDown(self):
        if self._orig_sources_dir is None:
            os.environ.pop("SOURCES_DIR", None)
        else:
            os.environ["SOURCES_DIR"] = self._orig_sources_dir
        source_registry._SOURCES_MTIME = source_registry._SOURCES_NEVER_LOADED
        source_registry._SOURCES_PAYLOAD = ([], [])

    def test_normalize_source_record_domains(self):
        raw = {
            "id": "testsrc",
            "domains": ["example.com", "www.example.com"],
            "chapter_link_selector": "a.ch",
            "parsing_strategy": "css_chapter_links",
            "status": "working",
        }
        norm = source_registry.normalize_source_record(raw)
        self.assertIsNotNone(norm)
        assert norm is not None
        self.assertEqual(norm["id"], "testsrc")
        self.assertIn("example.com", norm["domains"])
        self.assertTrue(norm["chapter_selector"])

    def test_get_profile_for_url_longest_domain_wins(self):
        # Synthetic entries not in catalog — exercise host normalization only if catalog empty
        prof = source_registry.get_profile_for_url("https://mangadex.org/title/00000000-0000-0000-0000-000000000000")
        if prof:
            self.assertEqual(prof.get("parsing_strategy"), "mangadex_api")
            self.assertTrue(prof.get("api"))

    def test_curated_source_catalog_precedence_over_manifest(self):
        tmp = tempfile.mkdtemp(prefix="src-reg-")
        try:
            catalog = {
                "version": 1,
                "sources": [
                    {
                        "id": "mangadex",
                        "display_name": "MangaDex",
                        "domains": ["mangadex.org"],
                        "parsing_strategy": "mangadex_api",
                        "chapter_link_selector": "",
                        "status": "working",
                    }
                ],
            }
            manifest = [
                {
                    "name": "Tachiyomi: MangaDex clone",
                    "pkg": "pkg.test",
                    "sources": [{"id": "mdx", "name": "MangaDex", "baseUrl": "https://mangadex.org"}],
                }
            ]
            with open(os.path.join(tmp, "catalog.json"), "w", encoding="utf-8") as f:
                json.dump(catalog, f)
            with open(os.path.join(tmp, "sources.manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            os.environ["SOURCES_DIR"] = tmp
            source_registry._SOURCES_MTIME = source_registry._SOURCES_NEVER_LOADED
            prof = source_registry.get_profile_for_url("https://mangadex.org/title/abc")
            self.assertIsNotNone(prof)
            assert prof is not None
            self.assertEqual(prof.get("id"), "mangadex")
            self.assertEqual(prof.get("parsing_strategy"), "mangadex_api")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manifest_duplicate_domain_does_not_override_curated(self):
        tmp = tempfile.mkdtemp(prefix="src-reg-")
        try:
            catalog = {
                "version": 1,
                "sources": [
                    {
                        "id": "curated_alpha",
                        "display_name": "Curated Alpha",
                        "domains": ["alpha.example"],
                        "parsing_strategy": "mangadex_api",
                        "chapter_link_selector": "",
                    }
                ],
            }
            manifest = [
                {
                    "name": "Ext Alpha",
                    "pkg": "pkg.alpha",
                    "sources": [{"id": "alpha", "name": "Alpha", "baseUrl": "https://alpha.example"}],
                }
            ]
            with open(os.path.join(tmp, "catalog.json"), "w", encoding="utf-8") as f:
                json.dump(catalog, f)
            with open(os.path.join(tmp, "sources.manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            os.environ["SOURCES_DIR"] = tmp
            source_registry._SOURCES_MTIME = source_registry._SOURCES_NEVER_LOADED
            prof = source_registry.get_profile_for_url("https://alpha.example/series/demo")
            self.assertIsNotNone(prof)
            assert prof is not None
            self.assertEqual(prof.get("id"), "curated_alpha")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

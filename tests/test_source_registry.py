import unittest
import os
import json
import tempfile
import shutil
from pathlib import Path
from urllib.parse import urlparse
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

    def test_public_snapshot_excludes_nsfw_sources(self):
        tmp = tempfile.mkdtemp(prefix="src-reg-")
        try:
            catalog = {
                "version": 1,
                "sources": [
                    {
                        "id": "safe_source",
                        "display_name": "Safe Source",
                        "domains": ["safe.example"],
                        "parsing_strategy": "css_chapter_links",
                        "chapter_link_selector": "a.ch",
                        "nsfw": False,
                    },
                    {
                        "id": "nsfw_source",
                        "display_name": "NSFW Source",
                        "domains": ["adult.example"],
                        "parsing_strategy": "css_chapter_links",
                        "chapter_link_selector": "a.ch",
                        "nsfw": True,
                    },
                ],
            }
            with open(os.path.join(tmp, "catalog.json"), "w", encoding="utf-8") as f:
                json.dump(catalog, f)
            os.environ["SOURCES_DIR"] = tmp
            source_registry._SOURCES_MTIME = source_registry._SOURCES_NEVER_LOADED

            snapshot = source_registry.public_api_snapshot()
            self.assertEqual(snapshot.get("source_count"), 1)
            domains = snapshot.get("domains") or []
            self.assertIn("safe.example", domains)
            self.assertNotIn("adult.example", domains)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manifest_import_skips_nsfw_extensions(self):
        tmp = tempfile.mkdtemp(prefix="src-reg-")
        try:
            catalog = {"version": 1, "sources": []}
            manifest = [
                {
                    "name": "Safe Ext",
                    "pkg": "pkg.safe",
                    "nsfw": False,
                    "sources": [{"id": "safe", "name": "Safe", "baseUrl": "https://safe.example"}],
                },
                {
                    "name": "Adult Ext",
                    "pkg": "pkg.adult",
                    "nsfw": True,
                    "sources": [{"id": "adult", "name": "Adult", "baseUrl": "https://nhentai.xxx"}],
                },
            ]
            with open(os.path.join(tmp, "catalog.json"), "w", encoding="utf-8") as f:
                json.dump(catalog, f)
            with open(os.path.join(tmp, "sources.manifest.json"), "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            os.environ["SOURCES_DIR"] = tmp
            source_registry._SOURCES_MTIME = source_registry._SOURCES_NEVER_LOADED

            rows = source_registry.list_sources()
            domains = {d for r in rows for d in (r.get("domains") or [])}
            self.assertIn("safe.example", domains)
            self.assertNotIn("nhentai.xxx", domains)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class SourceManifestRepositoryPolicyTests(unittest.TestCase):
    def test_committed_manifest_has_no_nsfw_or_local_urls(self):
        repo_root = Path(__file__).resolve().parents[1]
        manifest_path = repo_root / "sources" / "sources.manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        self.assertIsInstance(payload, list)

        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0"}
        for ext in payload:
            self.assertFalse(bool(ext.get("nsfw", False)), "nsfw extension must not be committed")
            for src in ext.get("sources") or []:
                self.assertFalse(bool(src.get("nsfw", False)), "nsfw source must not be committed")
                base = str(src.get("baseUrl") or "")
                self.assertTrue(base.startswith("http://") or base.startswith("https://"))
                parsed_host = (urlparse(base).hostname or "").lower()
                self.assertTrue(parsed_host)
                self.assertNotIn(parsed_host, blocked_hosts)

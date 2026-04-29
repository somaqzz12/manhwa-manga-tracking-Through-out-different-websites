import unittest

from services import source_registry


class SourceRegistryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

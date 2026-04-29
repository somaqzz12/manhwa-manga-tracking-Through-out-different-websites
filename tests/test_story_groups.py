import unittest

from services import story_groups


class StoryGroupTests(unittest.TestCase):
    def test_aggregate_picks_max_latest_across_sources(self):
        rows = [
            {
                "id": 1,
                "title": "Same",
                "url": "https://a.example/m/x",
                "story_id": "sg-test",
                "latest_seen_num": 174.0,
                "latest_seen_url": "https://a.example/m/x/174",
                "latest_seen": "Ch 174",
                "read_chapter_num": 170.0,
                "read_source_url": "https://a.example/m/x/170",
                "read_chapter_label": "Ch 170",
                "new_update": 1,
                "cover_url": None,
                "last_error": None,
                "latest_parser_version": "a",
                "series_key": None,
            },
            {
                "id": 2,
                "title": "Same longer title",
                "url": "https://b.example/t/y",
                "story_id": "sg-test",
                "latest_seen_num": 176.0,
                "latest_seen_url": "https://b.example/ch/176",
                "latest_seen": "Ch 176",
                "read_chapter_num": 170.0,
                "read_source_url": "https://b.example/ch/170",
                "read_chapter_label": "Ch 170",
                "new_update": 1,
                "cover_url": None,
                "last_error": None,
                "latest_parser_version": "b",
                "series_key": None,
            },
        ]
        merged = story_groups.aggregate_story_items(rows)
        self.assertEqual(merged["latest_seen_num"], 176.0)
        self.assertEqual(merged["source_count"], 2)
        self.assertIn("176", (merged.get("latest_seen_url") or ""))


if __name__ == "__main__":
    unittest.main()

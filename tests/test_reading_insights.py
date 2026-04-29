import unittest

from services import reading_insights


class ReadingInsightsTests(unittest.TestCase):
    def test_rank_next_up_prefers_unread_and_new(self):
        cards = [
            {"id": 1, "title": "Alpha", "unread_count": 0, "new_update": 0, "_added_id": 10},
            {"id": 2, "title": "Beta", "unread_count": 3, "new_update": 0, "_added_id": 9},
            {"id": 3, "title": "Gamma", "unread_count": 1, "new_update": 1, "_added_id": 8},
        ]
        out = reading_insights.rank_next_up(cards, {})
        self.assertEqual([c["title"] for c in out], ["Gamma", "Beta", "Alpha"])


if __name__ == "__main__":
    unittest.main()

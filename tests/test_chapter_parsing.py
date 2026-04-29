import unittest

from bs4 import BeautifulSoup

from services import chapter_parsing as chapter


class ChapterParsingTests(unittest.TestCase):
    def test_parse_chapter_number(self):
        self.assertEqual(chapter.parse_chapter_number("Chapter 123"), 123.0)
        self.assertEqual(chapter.parse_chapter_number("Ep. 12.5"), 12.5)
        self.assertIsNone(chapter.parse_chapter_number("No chapter here"))

    def test_parse_chapter_from_url(self):
        self.assertEqual(chapter.parse_chapter_from_url("https://x.test/manga/a/chapter/88"), 88.0)
        self.assertEqual(chapter.parse_chapter_from_url("https://x.test/manga/a/c156"), 156.0)
        self.assertEqual(chapter.parse_chapter_from_url("https://x.test/read/abc/episode-12.5"), 12.5)
        self.assertIsNone(chapter.parse_chapter_from_url("https://x.test/read/abc/index"))

    def test_candidate_scoring_prefers_same_series_highest_chapter(self):
        html = """
        <html><head><title>Series X</title></head><body>
          <a href="/manga/series-x/chapter-9">Chapter 9</a>
          <a href="/manga/series-x/chapter-10">Chapter 10</a>
          <a href="/manga/other-series/chapter-999">Chapter 999</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        picked = chapter.pick_best_candidate_with_debug(soup, "https://reader.example/manga/series-x")
        self.assertEqual(picked["chapter_num"], 10.0)
        self.assertIn("series-x", (picked["chapter_url"] or ""))
        self.assertGreaterEqual(picked["confidence"], 0.55)


if __name__ == "__main__":
    unittest.main()

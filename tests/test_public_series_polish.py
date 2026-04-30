"""Source comparison page (/series/<slug>): recommendation, empty state, NSFW filtering."""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402


class PublicSeriesPolishTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.old_db_path = app.DB_PATH
        self.old_db_ready = app.DB_READY
        app.DB_PATH = self.db_path
        app.DB_READY = False
        app.app.config["TESTING"] = True
        app.app.config["WTF_CSRF_ENABLED"] = False
        app.ensure_db_ready()
        self.client = app.app.test_client()

    def tearDown(self):
        app.DB_PATH = self.old_db_path
        app.DB_READY = self.old_db_ready
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_solo_leveling_catalog_shows_recommended_and_mangadex_primary(self):
        res = self.client.get("/series/solo-leveling")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Open original site", body)
        self.assertIn("Recommended", body)
        self.assertIn("mangadex.org/title", body)
        self.assertIn("Track manually", body)

    def test_normalized_series_shows_source_rows_and_open_original(self):
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO series (slug, norm_title_key, title, canonical_title, description, cover_url, type, status, created_at, updated_at)
                VALUES ('polish-norm', 'polish norm', 'Polish Norm', NULL, 'Desc', NULL, 'manga', 'unknown', ?, ?)
                """,
                (now, now),
            )
            sid = int(conn.execute("SELECT id FROM series WHERE slug = 'polish-norm'").fetchone()["id"])
            conn.execute(
                """
                INSERT INTO series_source (
                    series_id, source_name, source_domain, source_url, normalized_source_url,
                    support_level, source_policy, detection_source,
                    latest_chapter, latest_chapter_url, chapter_count, health_status, created_at, updated_at
                )
                VALUES (?, 'Reader', 'read.example', 'https://read.example/p', 'https://read.example/p',
                    'site_adapter', 'standard', 'manual', '10', NULL, 10, 'working', ?, ?)
                """,
                (sid, now, now),
            )
        with patch.object(app.source_registry, "get_profile_for_url", return_value=None):
            page = self.client.get("/series/polish-norm")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("Reader", text)
        self.assertIn("read.example", text)
        self.assertIn('href="https://read.example/p"', text)
        self.assertIn("Recommended", text)

    def test_empty_sources_normalized_series_message(self):
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO series (slug, norm_title_key, title, description, cover_url, type, status, created_at, updated_at)
                VALUES ('empty-norm', 'empty norm', 'Empty Norm', NULL, NULL, 'manga', 'unknown', ?, ?)
                """,
                (now, now),
            )
        page = self.client.get("/series/empty-norm")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("No sources saved yet.", text)
        self.assertIn("Paste a URL", text)

    def test_nsfw_source_row_hidden_on_public_series(self):
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO series (slug, norm_title_key, title, description, cover_url, type, status, created_at, updated_at)
                VALUES ('nsfw-norm', 'nsfw norm', 'Nsfw Norm', NULL, NULL, 'manga', 'unknown', ?, ?)
                """,
                (now, now),
            )
            sid = int(conn.execute("SELECT id FROM series WHERE slug = 'nsfw-norm'").fetchone()["id"])
            conn.execute(
                """
                INSERT INTO series_source (
                    series_id, source_name, source_domain, source_url, normalized_source_url,
                    support_level, source_policy, detection_source,
                    latest_chapter, chapter_count, health_status, created_at, updated_at
                )
                VALUES (?, 'Safe', 'safe.example', 'https://safe.example/m', 'https://safe.example/m',
                    'site_adapter', 'standard', 'manual', '1', 1, 'working', ?, ?)
                """,
                (sid, now, now),
            )
            conn.execute(
                """
                INSERT INTO series_source (
                    series_id, source_name, source_domain, source_url, normalized_source_url,
                    support_level, source_policy, detection_source,
                    latest_chapter, chapter_count, health_status, created_at, updated_at
                )
                VALUES (?, 'Bad', 'bad.example', 'https://bad.example/m', 'https://bad.example/m',
                    'official_api', 'standard', 'manual', '9', 9, 'working', ?, ?)
                """,
                (sid, now, now),
            )

        def _prof(url: str):
            u = str(url or "")
            if "bad.example" in u:
                return {"id": "bad", "nsfw": True}
            return None

        with patch.object(app.source_registry, "get_profile_for_url", side_effect=_prof):
            page = self.client.get("/series/nsfw-norm")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("Safe", text)
        self.assertNotIn("Bad", text)
        self.assertNotIn("bad.example", text)

    def test_manual_catalog_source_shows_track_manually(self):
        res = self.client.get("/series/solo-leveling")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Manual/Other", body)
        self.assertIn("Track manually", body)

    def test_discover_view_sources_links_normalized_slug_when_title_matches(self):
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO series (slug, norm_title_key, title, description, cover_url, type, status, created_at, updated_at)
                VALUES ('custom-solo-slug', 'solo leveling', 'Solo Leveling', NULL, NULL, 'manga', 'unknown', ?, ?)
                """,
                (now, now),
            )
        page = self.client.get("/discover")
        self.assertEqual(page.status_code, 200)
        body = page.get_data(as_text=True)
        self.assertIn("/series/custom-solo-slug", body)


if __name__ == "__main__":
    unittest.main()

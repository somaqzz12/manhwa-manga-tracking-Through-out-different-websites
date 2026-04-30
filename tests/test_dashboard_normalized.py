"""Dashboard dual-read: UserLibraryItem + Series + SeriesSource with bookmark fallback."""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402
from services import library_model  # noqa: E402


def _insert_uli(
    conn,
    *,
    user_id: int,
    title: str,
    slug: str,
    source_url: str,
    cover_url: str | None = None,
    latest_chapter: str | None = "12",
    latest_chapter_url: str | None = None,
) -> None:
    now = app._now_iso_z()
    norm_key = library_model.normalize_title(title)
    norm_src = library_model.normalize_source_url(source_url)
    conn.execute(
        """
        INSERT INTO series (slug, norm_title_key, title, canonical_title, description, cover_url, type, status, created_at, updated_at)
        VALUES (?, ?, ?, NULL, NULL, ?, 'manga', 'unknown', ?, ?)
        """,
        (slug, norm_key, title, cover_url or None, now, now),
    )
    sid = int(conn.execute("SELECT id FROM series WHERE slug = ?", (slug,)).fetchone()["id"])
    ch_url = latest_chapter_url or source_url
    conn.execute(
        """
        INSERT INTO series_source (
            series_id, source_name, source_domain, source_url, normalized_source_url,
            support_level, source_policy, detection_source,
            latest_chapter, latest_chapter_url, chapter_count, health_status, created_at, updated_at
        )
        VALUES (?, 'TestSrc', 'testsrc.example', ?, ?, 'site_adapter', 'standard', 'manual', ?, ?, 50, 'working', ?, ?)
        """,
        (sid, source_url, norm_src, latest_chapter, ch_url, now, now),
    )
    ssid = int(
        conn.execute("SELECT id FROM series_source WHERE normalized_source_url = ?", (norm_src,)).fetchone()["id"]
    )
    conn.execute(
        """
        INSERT INTO user_library_item (user_id, series_id, preferred_source_id, status, notifications_enabled, created_at, updated_at)
        VALUES (?, ?, ?, 'active', 0, ?, ?)
        """,
        (user_id, sid, ssid, now, now),
    )


class DashboardNormalizedDualReadTests(unittest.TestCase):
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

    def _make_user(self, email: str = "dashnorm@example.com") -> int:
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("dashuser", email, generate_password_hash("secret12"), now),
            )
            return int(conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"])

    def test_dashboard_shows_normalized_library_item(self):
        uid = self._make_user()
        listing = "https://reader.example.com/norm-dash-only"
        ch_url = "https://reader.example.com/norm-dash-only/read/99"
        with app.get_conn() as conn:
            _insert_uli(
                conn,
                user_id=uid,
                title="Norm Dash Only",
                slug="norm-dash-only",
                source_url=listing,
                cover_url="https://cdn.example/c.jpg",
                latest_chapter="99",
                latest_chapter_url=ch_url,
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", return_value=True):
            res = self.client.get("/app")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Norm Dash Only", body)
        self.assertIn("TestSrc", body)
        self.assertIn("testsrc.example", body)
        self.assertIn(ch_url, body)
        self.assertIn("Supported", body)

    def test_dashboard_falls_back_to_legacy_bookmark(self):
        uid = self._make_user("legacy@example.com")
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO bookmarks (user_id, title, url, story_id, created_at, cover_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    "Legacy Bookmark Title",
                    "https://legacy.example/manga/one",
                    app.story_groups.new_solo_story_id(),
                    now,
                    "",
                ),
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/app")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Legacy Bookmark Title", res.get_data(as_text=True))

    def test_duplicate_normalized_and_bookmark_single_card(self):
        uid = self._make_user("dedupe@example.com")
        listing = "https://dup.example.com/manga/x"
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO bookmarks (user_id, title, url, story_id, created_at, cover_url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    "Dup Title",
                    listing,
                    app.story_groups.new_solo_story_id(),
                    now,
                    "",
                ),
            )
            _insert_uli(
                conn,
                user_id=uid,
                title="Dup Title Longer",
                slug="dup-title",
                source_url=listing,
                cover_url=None,
                latest_chapter="5",
            )
        raw, rid = app._fetch_user_story_rows(uid, "")
        cards = app._build_sorted_story_cards(raw, rid, "added")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].get("source_count"), 1)

    def test_continue_uses_preferred_chapter_url(self):
        uid = self._make_user("cont@example.com")
        listing = "https://cont.example/list"
        ch_url = "https://cont.example/list/chapter-42"
        with app.get_conn() as conn:
            _insert_uli(
                conn,
                user_id=uid,
                title="Continue Me",
                slug="continue-me",
                source_url=listing,
                latest_chapter="42",
                latest_chapter_url=ch_url,
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/app")
        body = res.get_data(as_text=True)
        self.assertIn('href="' + ch_url + '"', body)

    def test_missing_cover_shows_placeholder(self):
        uid = self._make_user("nocov@example.com")
        with app.get_conn() as conn:
            _insert_uli(
                conn,
                user_id=uid,
                title="No Cover Series",
                slug="no-cover-ser",
                source_url="https://nocov.example/m",
                cover_url=None,
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/app")
        body = res.get_data(as_text=True)
        self.assertIn("No Cover Series", body)
        self.assertIn("story-cover-placeholder", body)


if __name__ == "__main__":
    unittest.main()

"""Tracker MVP defaults: no discover/demo surfaces; library chapter actions."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402
import config  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


class TrackerMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._flag = patch.object(config, "SHOW_DEMO_CONTENT", False)
        self._flag.start()
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

    def tearDown(self) -> None:
        self._flag.stop()
        app.DB_PATH = self.old_db_path
        app.DB_READY = self.old_db_ready
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _login(self) -> int:
        with app.get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("tuser", "tuser@example.com", generate_password_hash("secret1234"), app._now_iso_z()),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("tuser@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        return uid

    def test_homepage_has_no_demo_shelves_by_default(self) -> None:
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("Track manga and manhwa", body)
        self.assertNotIn("Starter picks", body)
        self.assertNotIn("landing_trending", body)

    def test_logged_in_root_redirects_to_dashboard(self) -> None:
        self._login()
        r = self.client.get("/", follow_redirects=False)
        self.assertIn(r.status_code, (302, 303))
        self.assertIn("/dashboard", r.headers.get("Location", ""))

    def test_discover_nav_not_in_tracker_home(self) -> None:
        body = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("/discover", body)

    def test_discover_page_is_coming_later(self) -> None:
        body = self.client.get("/discover").get_data(as_text=True)
        self.assertIn("not available", body.lower())

    def test_demo_search_api_404(self) -> None:
        self.assertEqual(self.client.get("/api/demo/search?q=x").status_code, 404)

    def test_dashboard_loads_logged_in(self) -> None:
        self._login()
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Library", r.get_data(as_text=True))

    def test_add_manual_url_creates_item(self) -> None:
        uid = self._login()
        r = self.client.post(
            "/add",
            data={
                "title": "Solo Leveling",
                "url": "https://asuracomic.net/series/solo-leveling",
                "current_chapter": "45",
                "latest_chapter": "52",
            },
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 303))
        with app.get_conn() as conn:
            row = conn.execute(
                "SELECT title, latest_seen_num FROM bookmarks WHERE user_id = ?",
                (uid,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("Solo", str(row["title"]))
        self.assertEqual(float(row["latest_seen_num"]), 52.0)

    def test_increment_and_mark_caught_up_and_edit(self) -> None:
        uid = self._login()
        self.client.post(
            "/add",
            data={
                "title": "T",
                "url": "https://example.com/manga/t",
                "current_chapter": "10",
                "latest_chapter": "15",
            },
        )
        with app.get_conn() as conn:
            bid = int(conn.execute("SELECT id FROM bookmarks WHERE user_id = ?", (uid,)).fetchone()["id"])
        self.client.post(f"/library/{bid}/increment-current")
        with app.get_conn() as conn:
            rp = conn.execute(
                "SELECT chapter_num FROM reading_progress WHERE bookmark_id = ? ORDER BY id DESC LIMIT 1",
                (bid,),
            ).fetchone()
        self.assertIsNotNone(rp)
        self.assertEqual(float(rp["chapter_num"]), 11.0)
        self.client.post(f"/library/{bid}/mark-caught-up")
        with app.get_conn() as conn:
            rp2 = conn.execute(
                "SELECT chapter_num FROM reading_progress WHERE bookmark_id = ? ORDER BY id DESC LIMIT 1",
                (bid,),
            ).fetchone()
        self.assertEqual(float(rp2["chapter_num"]), 15.0)
        self.client.post(
            f"/library/{bid}/update-chapters",
            data={
                "title": "T2",
                "url": "https://example.com/manga/t",
                "current_chapter": "12",
                "latest_chapter": "20",
                "notes": "hello",
            },
        )
        with app.get_conn() as conn:
            b = conn.execute("SELECT title, notes, latest_seen_num FROM bookmarks WHERE id = ?", (bid,)).fetchone()
        self.assertEqual(str(b["title"]), "T2")
        self.assertIn("hello", str(b["notes"] or ""))
        self.assertEqual(float(b["latest_seen_num"]), 20.0)

    def test_extension_progress_updates_read_and_optional_latest(self) -> None:
        uid = self._login()
        self.client.post(
            "/api/series/ensure",
            json={
                "title": "Ext Series",
                "url": "https://example.com/manga/ext-track",
                "source_domain": "example.com",
            },
        )
        with app.get_conn() as conn:
            bid = int(conn.execute("SELECT id FROM bookmarks WHERE user_id = ?", (uid,)).fetchone()["id"])
        self.client.post(
            "/api/progress",
            json={
                "series_url": "https://example.com/manga/ext-track",
                "chapter_num": 7,
                "chapter_label": "Ch 7",
                "latest_chapter_num": 9,
            },
        )
        with app.get_conn() as conn:
            b = conn.execute("SELECT latest_seen_num FROM bookmarks WHERE id = ?", (bid,)).fetchone()
            rp = conn.execute(
                "SELECT chapter_num FROM reading_progress WHERE bookmark_id = ? ORDER BY id DESC LIMIT 1",
                (bid,),
            ).fetchone()
        self.assertEqual(float(rp["chapter_num"]), 7.0)
        self.assertEqual(float(b["latest_seen_num"]), 9.0)


if __name__ == "__main__":
    unittest.main()

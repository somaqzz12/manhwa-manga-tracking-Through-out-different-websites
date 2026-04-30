import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402


class AppRegressionTests(unittest.TestCase):
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

    def test_admin_pages_work_on_fresh_sqlite_schema(self):
        users = self.client.get("/admin/users")
        self.assertEqual(users.status_code, 200)

        detail = self.client.get("/admin/users/1")
        self.assertEqual(detail.status_code, 200)

    def test_source_bug_report_url_does_not_duplicate_issues_path(self):
        href = app.build_source_bug_report_url(source_id="asurascans", domain="asurascans.com")
        self.assertIn("/issues/new?", href)
        self.assertNotIn("/issues/issues/new", href)

    def test_unread_count_includes_tracked_url_norms(self):
        # Register + login would be heavy; hit API with session after creating bookmark via internal API
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("tuser", "tuser@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("tuser@example.com",)).fetchone()
            uid = int(uid_row["id"])
            conn.execute(
                """
                INSERT INTO bookmarks (user_id, title, url, story_id, created_at, series_key)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    uid,
                    "Manual",
                    "https://example.com/manga/test-series",
                    app.story_groups.new_solo_story_id(),
                    now,
                ),
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/api/unread-count")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload.get("ok"))
        norms = payload.get("tracked_url_norms") or []
        self.assertIn("https://example.com/manga/test-series".rstrip("/").lower(), norms)

    def test_alt_sources_uses_generated_health_check_status(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("altuser", "altuser@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("altuser@example.com",)).fetchone()
            uid = int(uid_row["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid

        sources = [
            {"id": "current", "display_name": "Current", "domains": ["current.example"]},
            {"id": "healthy", "display_name": "Healthy", "domains": ["healthy.example"]},
            {"id": "broken", "display_name": "Broken", "domains": ["broken.example"]},
        ]
        health = {
            "by_id": {
                "healthy": {"check_status": "working"},
                "broken": {"check_status": "broken"},
            }
        }

        with (
            patch.object(app, "is_public_http_url", return_value=True),
            patch.object(app.source_registry, "get_profile_for_url", return_value={"id": "current"}),
            patch.object(app.source_registry, "list_sources", return_value=sources),
            patch.object(app.source_registry, "load_health", return_value=health),
        ):
            res = self.client.get("/api/library/alt-sources?url=https://current.example/manga/demo")

        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload.get("ok"))
        ids = [row.get("id") for row in payload.get("alternatives") or []]
        self.assertIn("healthy", ids)
        self.assertNotIn("broken", ids)
        self.assertNotIn("current", ids)


if __name__ == "__main__":
    unittest.main()

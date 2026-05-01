"""Boring smoke tests for public pages and core flows (cleanup pass 1)."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402
import config  # noqa: E402


class CleanupPass1SmokeTests(unittest.TestCase):
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

    def test_get_home_returns_200(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)

    def test_get_sources_returns_200(self):
        r = self.client.get("/sources")
        self.assertEqual(r.status_code, 200)

    def test_get_demo_returns_404_when_disabled(self):
        with patch.object(config, "SHOW_DEMO_CONTENT", False):
            r = self.client.get("/demo")
            self.assertEqual(r.status_code, 404)

    def test_get_demo_returns_200_when_enabled(self):
        with patch.object(config, "SHOW_DEMO_CONTENT", True):
            r = self.client.get("/demo")
            self.assertEqual(r.status_code, 200)

    def test_dashboard_redirects_when_logged_out(self):
        r = self.client.get("/dashboard", follow_redirects=False)
        self.assertIn(r.status_code, (302, 303))

    def test_resolve_url_unsupported_does_not_crash(self):
        payload = {"url": "https://example.com/some/manga/page"}
        r = self.client.post("/api/resolve-url", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn(data.get("status"), ("manual", "supported", "error"))

    def test_manual_add_bookmark_post(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("smokeuser", "smoke@example.com", generate_password_hash("secret1234"), app._now_iso_z()),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("smoke@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        r = self.client.post(
            "/add",
            data={
                "title": "Manual Series",
                "url": "https://example.com/m/manual-series",
            },
            follow_redirects=False,
        )
        self.assertIn(r.status_code, (302, 303))


if __name__ == "__main__":
    unittest.main()

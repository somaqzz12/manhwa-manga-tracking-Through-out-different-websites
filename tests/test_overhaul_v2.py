"""Overhaul v2: production honesty (no fake demo APIs), real catalog wiring."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import app  # noqa: E402
import config  # noqa: E402


class OverhaulV2Tests(unittest.TestCase):
    def setUp(self) -> None:
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
        app.DB_PATH = self.old_db_path
        app.DB_READY = self.old_db_ready
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_demo_api_endpoints_hidden_when_demo_flag_off(self) -> None:
        r_search = self.client.get("/api/demo/search?q=test")
        self.assertEqual(r_search.status_code, 404)
        r_track = self.client.post("/api/demo/track", json={"title": "X"})
        self.assertEqual(r_track.status_code, 404)

    def test_demo_dashboard_hidden_by_default(self) -> None:
        with patch.object(config, "SHOW_DEMO_CONTENT", False):
            r = self.client.get("/demo")
            self.assertEqual(r.status_code, 404)
        with patch.object(config, "SHOW_DEMO_CONTENT", True):
            r2 = self.client.get("/demo")
            self.assertEqual(r2.status_code, 200)

    def test_source_request_hidden_when_demo_flag_off(self) -> None:
        res = self.client.post("/api/source-request", json={"domain": "newsource.example", "title_hint": "Hint"})
        self.assertEqual(res.status_code, 404)

    def test_source_request_persists_when_demo_flag_on(self) -> None:
        with patch.object(config, "SHOW_DEMO_CONTENT", True):
            res = self.client.post("/api/source-request", json={"domain": "newsource.example", "title_hint": "Hint"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))
        with app.get_conn() as conn:
            row = conn.execute(
                "SELECT domain, title_hint FROM source_requests WHERE domain = ?",
                ("newsource.example",),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("Hint", str(row["title_hint"] or ""))

    def test_series_sources_api_not_hardcoded_when_missing(self) -> None:
        res = self.client.get("/api/series/999999999/sources")
        self.assertEqual(res.status_code, 404)
        self.assertFalse((res.get_json() or {}).get("ok"))

    @patch("app.scrape_series_cover", return_value="")
    def test_extension_ensure_creates_normalized_library_row(self, _cover) -> None:
        from datetime import datetime, timezone

        from werkzeug.security import generate_password_hash

        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        with app.get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("exuser", "exuser@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("exuser@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.post(
            "/api/series/ensure",
            json={
                "title": "Extension Title",
                "url": "https://example.com/manga/ext-series",
                "source_domain": "example.com",
                "synced_at": "2026-05-01T12:00:00Z",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))
        with app.get_conn() as conn:
            ss = conn.execute(
                "SELECT id FROM series_source WHERE instr(lower(source_domain), 'example.com') > 0 "
                "OR instr(lower(source_url), 'example.com') > 0",
            ).fetchone()
            self.assertIsNotNone(ss)
            uli = conn.execute(
                "SELECT id FROM user_library_item WHERE user_id = ?",
                (uid,),
            ).fetchone()
            self.assertIsNotNone(uli)


if __name__ == "__main__":
    unittest.main()

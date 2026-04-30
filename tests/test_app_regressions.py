import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402
from sources.base import SourcePreview


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

    def test_api_resolve_url_manual_fallback_on_detection_failure(self):
        with patch.object(app, "is_public_http_url", return_value=True), patch.object(
            app, "source_engine_resolve_url", side_effect=RuntimeError("boom")
        ):
            res = self.client.post("/api/resolve-url", json={"url": "https://unknown.example/series/test"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("support_level"), "manual_only")
        self.assertEqual(payload.get("status"), "manual")

    def test_unknown_domain_falls_back_to_generic_or_manual_safely(self):
        preview = SourcePreview(
            source_name="Unknown Site",
            source_url="https://mangadexx.org/title/fake",
            support_level="manual_only",
            confidence=0.2,
            title="",
            warnings=["Automatic detection failed"],
        )
        with patch.object(app, "is_public_http_url", return_value=True), patch.object(
            app, "source_engine_resolve_url", return_value=preview
        ):
            res = self.client.post("/api/resolve-url", json={"url": "https://mangadexx.org/title/fake"})
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertTrue(payload.get("ok"))
        self.assertIn(payload.get("support_level"), ("manual_only", "generic_detector"))

    def test_resolve_url_supported_then_manual_contract(self):
        supported = SourcePreview(
            source_name="MangaDex",
            source_url="https://mangadex.org/title/abc",
            support_level="official_api",
            confidence=0.95,
            title="Demo",
            latest_chapter="123",
        )
        manual = SourcePreview(
            source_name="Unknown Site",
            source_url="https://unknown.example/title/abc",
            support_level="manual_only",
            confidence=0.1,
            title="",
        )
        with patch.object(app, "is_public_http_url", return_value=True), patch.object(
            app, "source_engine_resolve_url", side_effect=[supported, manual]
        ):
            ok_res = self.client.post("/api/resolve-url", json={"url": "https://mangadex.org/title/abc"})
            manual_res = self.client.post("/api/resolve-url", json={"url": "https://unknown.example/title/abc"})
        self.assertEqual(ok_res.status_code, 200)
        self.assertEqual(manual_res.status_code, 200)
        self.assertEqual((ok_res.get_json() or {}).get("status"), "supported")
        self.assertEqual((manual_res.get_json() or {}).get("support_level"), "manual_only")

    def test_resolve_url_rejects_private_and_invalid_schemes(self):
        bad_urls = [
            "http://localhost:8000",
            "http://127.0.0.1",
            "file:///etc/passwd",
            "ftp://example.com",
        ]
        for raw in bad_urls:
            res = self.client.post("/api/resolve-url", json={"url": raw})
            self.assertEqual(res.status_code, 400, msg=f"expected 400 for {raw}")
            payload = res.get_json() or {}
            self.assertFalse(payload.get("ok", False))

    def test_add_from_preview_manual_only_succeeds(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("previewuser", "preview@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("preview@example.com",)).fetchone()
            uid = int(uid_row["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", return_value=True):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "url": "https://unknown.example/series/demo-title",
                    "support_level": "manual_only",
                    "title": "Demo Title",
                    "latest_chapter": "12",
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("created"))

    def test_add_from_preview_duplicate_url_is_not_duplicated(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("dupeuser", "dupe@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("dupe@example.com",)).fetchone()
            uid = int(uid_row["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid

        with patch.object(app, "is_public_http_url", return_value=True):
            first = self.client.post(
                "/api/library/add-from-preview",
                json={"url": "https://mangadex.org/title/abc", "support_level": "official_api", "title": "Demo"},
            )
            second = self.client.post(
                "/api/library/add-from-preview",
                json={"url": "https://mangadex.org/title/abc", "support_level": "official_api", "title": "Demo"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        second_payload = second.get_json() or {}
        self.assertTrue(second_payload.get("duplicate"))

    def test_add_from_preview_saves_metadata_fields_when_provided(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("metauser", "meta@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("meta@example.com",)).fetchone()
            uid = int(uid_row["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid

        with patch.object(app, "is_public_http_url", return_value=True):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "url": "https://mangadex.org/title/abc",
                    "support_level": "official_api",
                    "title": "Display Title",
                    "canonical_title": "Canonical Title",
                    "description": "Metadata description",
                    "chapter_count": 123,
                    "cover_url": "https://img.example/cover.jpg",
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        series = payload.get("series") or {}
        added_url = series.get("url")
        self.assertTrue(added_url)
        with app.get_conn() as conn:
            row = conn.execute(
                "SELECT title, canonical_title, description, chapter_count, cover_url, url FROM bookmarks WHERE url = ? ORDER BY id DESC LIMIT 1",
                (added_url,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["title"], "Display Title")
        self.assertEqual(row["canonical_title"], "Canonical Title")
        self.assertEqual(row["description"], "Metadata description")
        self.assertEqual(int(row["chapter_count"]), 123)
        self.assertEqual(row["cover_url"], "https://img.example/cover.jpg")

    def test_add_from_preview_requires_authentication(self):
        res = self.client.post(
            "/api/library/add-from-preview",
            json={"url": "https://example.com/series/demo", "support_level": "manual_only", "title": "Demo"},
        )
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()

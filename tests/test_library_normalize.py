"""Normalized library model (Series / SeriesSource / UserLibraryItem) and dual-write from add-from-preview."""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402


class LibraryNormalizeTests(unittest.TestCase):
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

    def _make_user(self, email: str = "libnorm@example.com") -> int:
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("libnorm", email, generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            return int(uid_row["id"])

    def test_add_from_preview_creates_normalized_rows_and_bookmark(self):
        uid = self._make_user()
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        payload = {
            "source_url": "https://example.com/manga/test-normalize",
            "title": "Test Normalize Title",
            "canonical_title": "Test Normalize",
            "description": "A short description for the series.",
            "cover_url": "https://example.com/cover.jpg",
            "support_level": "manual_only",
            "chapter_count": 42,
            "latest_chapter": "12",
        }
        with patch.object(app, "is_public_http_url", return_value=True):
            res = self.client.post("/api/library/add-from-preview", json=payload)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body.get("ok"))
        self.assertTrue(body.get("created"))
        lib = body.get("library") or {}
        self.assertIn("series_id", lib)
        self.assertIn("series_source_id", lib)
        self.assertIn("user_library_item_id", lib)
        with app.get_conn() as conn:
            srow = conn.execute("SELECT * FROM series WHERE id = ?", (lib["series_id"],)).fetchone()
            self.assertIsNotNone(srow)
            self.assertEqual(str(srow["title"]), "Test Normalize Title")
            self.assertIn("short description", str(srow["description"] or ""))
            self.assertEqual(str(srow["cover_url"] or ""), "https://example.com/cover.jpg")
            src = conn.execute(
                "SELECT * FROM series_source WHERE id = ?",
                (lib["series_source_id"],),
            ).fetchone()
            self.assertIsNotNone(src)
            self.assertIn("example.com", str(src["source_url"]))
            self.assertEqual(int(src["chapter_count"] or 0), 42)
            uli = conn.execute(
                "SELECT * FROM user_library_item WHERE id = ?",
                (lib["user_library_item_id"],),
            ).fetchone()
            self.assertIsNotNone(uli)
            self.assertEqual(int(uli["user_id"]), uid)
            self.assertEqual(int(uli["preferred_source_id"]), int(lib["series_source_id"]))
            bm = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id = ? AND url LIKE ?",
                (uid, "%example.com/manga/test-normalize%"),
            ).fetchone()
            self.assertIsNotNone(bm)

    def test_duplicate_add_does_not_duplicate_source_or_uli(self):
        uid = self._make_user("dup@example.com")
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        payload = {
            "source_url": "https://example.com/manga/dedupe-test",
            "title": "Dedupe Title",
            "support_level": "site_adapter",
        }
        with patch.object(app, "is_public_http_url", return_value=True):
            r1 = self.client.post("/api/library/add-from-preview", json=payload)
            r2 = self.client.post("/api/library/add-from-preview", json=payload)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        j2 = r2.get_json()
        self.assertTrue(j2.get("duplicate"))
        lib1 = r1.get_json().get("library") or {}
        lib2 = j2.get("library") or {}
        self.assertEqual(lib1.get("series_source_id"), lib2.get("series_source_id"))
        with app.get_conn() as conn:
            n_src = conn.execute("SELECT COUNT(*) AS c FROM series_source").fetchone()
            self.assertEqual(int(n_src["c"]), 1)
            n_uli = conn.execute(
                "SELECT COUNT(*) AS c FROM user_library_item WHERE user_id = ?",
                (uid,),
            ).fetchone()
            self.assertEqual(int(n_uli["c"]), 1)

    def test_extension_assisted_normalized_without_backend_refetch(self):
        uid = self._make_user("ext@example.com")
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        payload = {
            "source_url": "https://scan.example/series/ext-meta",
            "title": "Extension Meta",
            "description": "From extension",
            "cover_url": "https://scan.example/cover.png",
            "support_level": "extension_assisted",
            "detection_source": "extension",
            "source_name": "Scan",
        }
        with patch.object(app, "is_public_http_url", return_value=True):
            res = self.client.post("/api/library/add-from-preview", json=payload)
        self.assertEqual(res.status_code, 200)
        lib = res.get_json().get("library") or {}
        with app.get_conn() as conn:
            src = conn.execute(
                "SELECT * FROM series_source WHERE id = ?",
                (lib["series_source_id"],),
            ).fetchone()
            self.assertEqual(str(src["detection_source"]), "extension")
            self.assertEqual(str(src["support_level"]), "extension_assisted")

    def test_public_series_page_shows_original_site_for_normalized_slug(self):
        with app.get_conn() as conn:
            now = app._now_iso_z()
            conn.execute(
                """
                INSERT INTO series (slug, norm_title_key, title, canonical_title, description, cover_url, type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'manga', 'unknown', ?, ?)
                """,
                (
                    "public-norm-slug",
                    "public norm",
                    "Public Norm",
                    "Public Norm",
                    "Desc here",
                    "https://example.com/c.jpg",
                    now,
                    now,
                ),
            )
            sid_row = conn.execute(
                "SELECT id FROM series WHERE slug = ?",
                ("public-norm-slug",),
            ).fetchone()
            sid = int(sid_row["id"])
            conn.execute(
                """
                INSERT INTO series_source (
                    series_id, source_name, source_domain, source_url, normalized_source_url,
                    support_level, source_policy, detection_source,
                    latest_chapter, latest_chapter_url, chapter_count, health_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)
                """,
                (
                    sid,
                    "Example Reader",
                    "reader.example",
                    "https://reader.example/m/public-norm",
                    "https://reader.example/m/public-norm".rstrip("/").lower(),
                    "site_adapter",
                    "standard",
                    "manual",
                    "99",
                    None,
                    100,
                    now,
                    now,
                ),
            )
        with patch.object(app.source_registry, "get_profile_for_url", return_value=None):
            page = self.client.get("/series/public-norm-slug")
        self.assertEqual(page.status_code, 200)
        text = page.get_data(as_text=True)
        self.assertIn("Open original site", text)
        self.assertIn("https://reader.example/m/public-norm", text)
        self.assertIn("Desc here", text)


if __name__ == "__main__":
    unittest.main()

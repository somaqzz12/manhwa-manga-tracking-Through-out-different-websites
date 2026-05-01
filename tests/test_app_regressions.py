import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DISABLE_AUTO_CHECK", "1")
os.environ.setdefault("FLASK_DEBUG", "1")

import app  # noqa: E402
from sources.base import SourcePreview


class AppRegressionTests(unittest.TestCase):
    def test_app_imports_without_cycles(self):
        import app as imported_app

        self.assertIsNotNone(imported_app.app)

    def test_non_test_modules_do_not_import_from_app(self):
        root = Path(__file__).resolve().parents[1]
        for py in root.rglob("*.py"):
            rel = py.relative_to(root).as_posix()
            if rel.startswith("tests/") or rel == "app.py":
                continue
            text = py.read_text(encoding="utf-8")
            self.assertNotIn("from app import", text, f"forbidden import in {rel}")

    def setUp(self):
        self._demo_flag_patcher = patch("config.SHOW_DEMO_CONTENT", True)
        self._demo_flag_patcher.start()
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
        self._demo_flag_patcher.stop()
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
            patch.object(app.source_registry, "list_public_sources", return_value=sources),
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

    def test_alt_sources_excludes_nsfw_candidates(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("altsafeuser", "altsafe@example.com", generate_password_hash("secret12"), now),
            )
            uid_row = conn.execute("SELECT id FROM users WHERE email = ?", ("altsafe@example.com",)).fetchone()
            uid = int(uid_row["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid

        safe_sources = [{"id": "safe", "display_name": "Safe", "domains": ["safe.example"], "nsfw": False}]
        with (
            patch.object(app, "is_public_http_url", return_value=True),
            patch.object(app.source_registry, "get_profile_for_url", return_value={"id": "current"}),
            patch.object(app.source_registry, "list_public_sources", return_value=safe_sources),
            patch.object(app.source_registry, "load_health", return_value={"by_id": {}}),
        ):
            res = self.client.get("/api/library/alt-sources?url=https://current.example/manga/demo")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        ids = [row.get("id") for row in payload.get("alternatives") or []]
        self.assertEqual(ids, ["safe"])

    def test_sources_page_excludes_nsfw_rows(self):
        safe_rows = [
            {
                "id": "safe",
                "display_name": "Safe Source",
                "domains": ["safe.example"],
                "status": "working",
                "nsfw": False,
                "health": {},
            }
        ]
        with (
            patch.object(app.source_registry, "public_sources_with_health", return_value=safe_rows),
            patch.object(app.source_registry, "aggregate_status_counts", return_value={"total": 1, "working": 1, "partial": 0, "broken": 0}),
            patch.object(app.source_registry, "load_health", return_value={}),
        ):
            res = self.client.get("/sources")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Safe Source", body)
        self.assertNotIn("nhentai.xxx", body)

    def test_extension_product_page_is_public(self):
        res = self.client.get("/extension")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Track manga from the sites you already use", body)
        self.assertIn("Safety", body)
        self.assertIn("scripting", body.lower())

    def test_homepage_has_unified_search_routing(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Title, or paste a series URL", body)
        self.assertIn('id="hero-discover-form"', body)
        self.assertIn('id="hero-q"', body)
        self.assertIn('window.location.href = addBase + "?url="', body)
        self.assertNotIn('window.location.href = discoverBase + "?url="', body)

    def test_public_drawer_uses_public_navigation_links(self):
        res = self.client.get("/discover")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('href="/">Home</a>', body)
        self.assertIn("Open App</a>", body)
        self.assertIn("Sign in</a>", body)
        self.assertIn("Create account</a>", body)
        self.assertNotIn(">Library</a>", body)
        self.assertNotIn("Import / Export</a>", body)

    def test_discover_url_error_hides_raw_exception_details(self):
        with patch.object(app, "source_engine_resolve_url", side_effect=RuntimeError("secret stack trace detail")):
            res = self.client.get("/discover?url=https%3A%2F%2Fbad.example%2Fseries")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Automatic detection could not read this URL.", body)
        self.assertNotIn("secret stack trace detail", body)

    def test_discover_q_url_uses_url_detection_block(self):
        preview = SourcePreview(
            source_name="MangaDex",
            source_url="https://mangadex.org/title/abc",
            support_level="official_api",
            confidence=0.95,
            title="Chainsaw Man",
            latest_chapter="200",
        )
        with patch.object(app, "source_engine_resolve_url", return_value=preview):
            res = self.client.get("/discover?q=https%3A%2F%2Fmangadex.org%2Ftitle%2Fabc")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("URL detection", body)
        self.assertIn("Chainsaw Man", body)
        self.assertIn("Support: Automatic", body)

    def test_discover_non_public_url_shows_unavailable(self):
        res = self.client.get("/discover?url=http%3A%2F%2Flocalhost%3A8080%2Fseries%2Fx")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Unavailable", body)
        self.assertIn("private, local, or blocked", body)

    def test_discover_query_specific_results_or_empty_state(self):
        from unittest.mock import patch

        from sources.adapters.mangadex import MangaDexAdapter

        fake_catalog_hit = [
            {
                "title": "Solo Leveling",
                "slug": "solo-leveling",
                "description": "Seeded catalog row for tests.",
                "cover_url": "",
                "type": "Manhwa",
                "source_count": 1,
                "sources_found": 1,
                "best_source": "MangaDex",
                "latest_chapter": None,
                "chapter_count": None,
                "source_url": "https://mangadex.org/title/00000000-0000-0000-0000-000000000001",
                "support_level": "official_api",
                "support_label": "Automatic",
                "is_demo": False,
                "source_name": "MangaDex",
                "comparison_slug": "solo-leveling",
            }
        ]
        with (
            patch("services.global_catalog.search.discover_rows_from_catalog", return_value=fake_catalog_hit),
            patch.object(MangaDexAdapter, "search", return_value=[]),
        ):
            hit = self.client.get("/discover?q=solo")
        self.assertEqual(hit.status_code, 200)
        hit_body = hit.get_data(as_text=True)
        self.assertIn('Results for "solo".', hit_body)
        self.assertIn("Solo Leveling", hit_body)
        self.assertNotIn("Search results · Demo", hit_body)

        with (
            patch("services.global_catalog.search.discover_rows_from_catalog", return_value=[]),
            patch.object(MangaDexAdapter, "search", return_value=[]),
        ):
            miss = self.client.get("/discover?q=zzzz-nothing-found-xyz")
        self.assertEqual(miss.status_code, 200)
        miss_body = miss.get_data(as_text=True)
        self.assertIn("No matches found", miss_body)
        self.assertNotIn("Solo Leveling", miss_body.split("Starter picks")[0])
        self.assertIn("Search supported sites live", miss_body)
        self.assertIn("Paste URL", miss_body)
        self.assertIn("discover-cover-fallback", miss_body)

    def test_discover_results_use_no_referrer_for_cover_images(self):
        from sources.adapters.mangadex import MangaDexAdapter

        fake = [
            {
                "source_id": "mangadex",
                "source_name": "MangaDex",
                "external_id": "abc-def-0000-0000-000000000001",
                "title": "Chainsaw Man",
                "url": "https://mangadex.org/title/abc-def-0000-0000-000000000001",
                "description": "On the page.",
                "cover_url": "https://uploads.mangadex.org/covers/abc/cover.jpg",
                "latest_chapter": "200",
                "chapter_count": 200,
                "support_level": "official_api",
            }
        ]
        with patch.object(MangaDexAdapter, "search", return_value=fake):
            res = self.client.get("/discover?q=chainsaw")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("discover-cover-fallback", body)
        # Discovery cards intentionally avoid MangaDex hotlink-blocked covers.
        self.assertNotIn("uploads.mangadex.org/covers/abc/cover.jpg", body)

    def test_discover_starter_picks_do_not_show_zero_sources_label(self):
        res = self.client.get("/discover")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertNotIn("0 sources", body)
        self.assertIn("Paste a source URL", body)

    def test_api_discover_search_returns_real_shaped_results(self):
        from unittest.mock import patch

        from sources.adapters.mangadex import MangaDexAdapter

        fake = [
            {
                "source_id": "mangadex",
                "source_name": "MangaDex",
                "external_id": "abc-def-0000-0000-000000000001",
                "title": "Chainsaw Man",
                "url": "https://mangadex.org/title/abc-def-0000-0000-000000000001",
                "description": "On the page.",
                "cover_url": "https://uploads.mangadex.org/covers/abc/cover.jpg",
                "latest_chapter": "200",
                "chapter_count": 200,
                "support_level": "official_api",
            }
        ]
        with (
            patch("services.global_catalog.search.discover_rows_from_catalog", return_value=[]),
            patch.object(MangaDexAdapter, "search", return_value=fake),
        ):
            res = self.client.get("/api/discover/search?q=chainsaw")
        self.assertEqual(res.status_code, 200)
        data = res.get_json() or {}
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("is_demo"))
        rows = data.get("results") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("title"), "Chainsaw Man")
        self.assertEqual(rows[0].get("support_level"), "official_api")
        self.assertIn("mangadex.org", rows[0].get("source_url") or "")
        self.assertIn("/api/image-proxy?url=", rows[0].get("cover_url") or "")

    def test_public_series_mangadex_uuid_uses_build_page(self):
        from unittest.mock import patch

        uid = "12345678-abcd-ef01-2345-6789abcdef01"

        def fake_build(slug: str):
            self.assertEqual(slug, uid.lower())
            return {
                "slug": uid,
                "title": "UUID Manga",
                "description": "About",
                "cover_url": "https://uploads.mangadex.org/covers/x/y.jpg",
                "source_preview": [
                    {
                        "source_name": "MangaDex",
                        "url": "https://mangadex.org/title/" + uid,
                        "latest_chapter": "5",
                        "support_level": "official_api",
                        "label": "Automatic",
                        "health_status": "working",
                    }
                ],
                "recommended_source": "MangaDex",
                "sources_count": 1,
                "missing_catalog_entry": False,
                "from_mangadex": True,
                "primary_add_url": "https://mangadex.org/title/" + uid,
            }

        with patch("app.metadata_discovery.build_series_page_from_mangadex_uuid", side_effect=fake_build):
            res = self.client.get(f"/series/{uid}")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("UUID Manga", body)
        self.assertIn("Open original site", body)
        self.assertIn("uploads.mangadex.org", body)

    def test_login_register_path_aliases(self):
        r1 = self.client.get("/login", follow_redirects=False)
        self.assertEqual(r1.status_code, 302)
        self.assertIn("/auth", r1.headers.get("Location", ""))
        r2 = self.client.get("/register", follow_redirects=False)
        self.assertEqual(r2.status_code, 302)
        self.assertIn("/auth", r2.headers.get("Location", ""))

    def test_auth_page_does_not_echo_open_redirect_in_next(self):
        res = self.client.get("/auth?next=https://evil.example/phish")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertNotIn("https://evil.example", body)

    def test_login_redirect_honors_safe_next_parameter(self):
        from urllib.parse import quote

        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("nextpathuser", "nextpathuser@example.com", generate_password_hash("secret1234"), now),
            )
        dest = "/app/add?title=Chainsaw+Man"
        res = self.client.post(
            f"/auth?next={quote(dest, safe='')}",
            data={"action": "login", "username": "nextpathuser", "password": "secret1234", "next": dest},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)
        loc = res.headers.get("Location", "")
        self.assertIn("/app/add", loc)

    def test_app_add_allows_unauthenticated_preview_with_prefill(self):
        res = self.client.get("/app/add?url=https%3A%2F%2Fexample.com%2Fm", follow_redirects=False)
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Add URL", body)
        self.assertIn("https://example.com/m", body)
        self.assertIn("requestSubmit()", body)

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
        series = second_payload.get("series") or {}
        self.assertIn("cover_url", series)
        self.assertIn("canonical_title", series)
        self.assertIn("source_name", series)
        self.assertIn("latest_seen_num", series)

    def test_add_from_preview_duplicate_returns_stored_metadata(self):
        """Second hit for same URL returns the same rich series row as created the first time."""
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("dupfull", "dupfull@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("dupfull@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid

        payload = {
            "source_url": "https://dupfull.example/series/meta",
            "support_level": "extension_assisted",
            "detection_source": "extension",
            "source_name": "ExampleSrc",
            "title": "Dup Full Title",
            "canonical_title": "Dup Full Canonical",
            "description": "Saved once",
            "cover_url": "https://dupfull.example/cover.jpg",
            "latest_chapter": "7",
        }
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")):
            first = self.client.post("/api/library/add-from-preview", json=payload)
            second = self.client.post(
                "/api/library/add-from-preview",
                json={**payload, "title": "Ignored on dupe"},
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue((first.get_json() or {}).get("created"))
        dup = second.get_json() or {}
        self.assertTrue(dup.get("duplicate"))
        s1 = (first.get_json() or {}).get("series") or {}
        s2 = dup.get("series") or {}
        for key in (
            "id",
            "url",
            "title",
            "canonical_title",
            "description",
            "cover_url",
            "source_name",
            "source_domain",
            "support_level",
            "detection_source",
            "latest_seen_num",
            "latest_seen_url",
        ):
            self.assertEqual(s2.get(key), s1.get(key), msg=f"mismatch on {key}")
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
                    "source_name": "MangaDex",
                    "source_domain": "mangadex.org",
                    "title": "Display Title",
                    "canonical_title": "Canonical Title",
                    "description": "Metadata description",
                    "chapter_count": 123,
                    "cover_url": "https://img.example/cover.jpg",
                    "latest_chapter": "Ch. 12",
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
                "SELECT title, canonical_title, description, chapter_count, cover_url, url, source_name, source_domain, support_level, latest_seen_num FROM bookmarks WHERE url = ? ORDER BY id DESC LIMIT 1",
                (added_url,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["title"], "Display Title")
        self.assertEqual(row["canonical_title"], "Canonical Title")
        self.assertEqual(row["description"], "Metadata description")
        self.assertEqual(int(row["chapter_count"]), 123)
        self.assertEqual(row["cover_url"], "https://img.example/cover.jpg")
        self.assertEqual(row["source_name"], "MangaDex")
        self.assertEqual(row["source_domain"], "mangadex.org")
        self.assertEqual(row["support_level"], "official_api")
        self.assertAlmostEqual(float(row["latest_seen_num"]), 12.0)

    def test_add_from_preview_accepts_extension_assisted_payload(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("extassist", "extassist@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("extassist@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/abc",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "From Extension",
                },
            )
        self.assertEqual(res.status_code, 200)
        payload = res.get_json() or {}
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("created"))

    def test_add_from_preview_extension_assisted_saves_cover_without_backend_refetch(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("extmeta", "extmeta@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("extmeta@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")), patch.object(
            app, "source_engine_resolve_url", side_effect=AssertionError("should not refetch backend resolver")
        ):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/extmeta",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "Browser Title",
                    "cover_url": "https://img.example/extmeta.jpg",
                },
            )
        self.assertEqual(res.status_code, 200)
        out = res.get_json() or {}
        self.assertTrue(out.get("ok"))
        added_url = (out.get("series") or {}).get("url")
        with app.get_conn() as conn:
            row = conn.execute("SELECT title, cover_url FROM bookmarks WHERE url = ?", (added_url,)).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["title"], "Browser Title")
        self.assertEqual(row["cover_url"], "https://img.example/extmeta.jpg")

    def test_add_from_preview_dedupes_extension_assisted_source_url(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("extdupe", "extdupe@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("extdupe@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")):
            first = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/dupe",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "Dupe",
                },
            )
            second = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/dupe/",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "Dupe 2",
                },
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue((second.get_json() or {}).get("duplicate"))

    def test_add_from_preview_ignores_invalid_cover_scheme(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("badcover", "badcover@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("badcover@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/cover",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "Cover Test",
                    "cover_url": "javascript:alert(1)",
                },
            )
        self.assertEqual(res.status_code, 200)
        added_url = ((res.get_json() or {}).get("series") or {}).get("url")
        with app.get_conn() as conn:
            row = conn.execute("SELECT cover_url FROM bookmarks WHERE url = ?", (added_url,)).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["cover_url"], "")

    def test_add_from_preview_requires_authentication(self):
        res = self.client.post(
            "/api/library/add-from-preview",
            json={"url": "https://example.com/series/demo", "support_level": "manual_only", "title": "Demo"},
        )
        self.assertEqual(res.status_code, 401)

    def test_dashboard_empty_state_shows_add_and_discover_actions(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("emptydash", "emptydash@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("emptydash@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/app")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('href="/app/add"', body)
        self.assertIn('href="/discover"', body)

    def test_discover_and_home_cards_have_real_action_hrefs(self):
        discover_res = self.client.get("/discover")
        self.assertEqual(discover_res.status_code, 200)
        discover_body = discover_res.get_data(as_text=True)
        self.assertIn("/series/", discover_body)
        self.assertIn("/app/add", discover_body)
        self.assertIn('action="/discover"', discover_body)

        home_res = self.client.get("/")
        self.assertEqual(home_res.status_code, 200)
        home_body = home_res.get_data(as_text=True)
        self.assertIn("/series/", home_body)
        self.assertIn("/app/add", home_body)
        self.assertIn("/discover?q=", home_body)

    def test_demo_sections_are_labeled(self):
        with (
            patch("config.SHOW_DEMO_CONTENT", True),
        ):
            discover_res = self.client.get("/discover")
        self.assertEqual(discover_res.status_code, 200)
        body = discover_res.get_data(as_text=True)
        self.assertIn("Starter picks · Demo", body)
        self.assertIn("Recently updated examples · Demo", body)
        self.assertIn("Source comparison example · Demo", body)

    def test_public_series_page_lists_sources(self):
        from services import discovery as disc_mod

        solo = next(x for x in disc_mod.LOCAL_DISCOVERY_CATALOG if str(x.get("slug") or "") == "solo-leveling")

        def _slug_demo_only(s: str):
            if (s or "").strip().lower() == "solo-leveling":
                return disc_mod._decorate_series(solo)
            return None

        with (
            patch("services.library_model.load_series_for_public_page", return_value=None),
            patch.object(app.discovery, "get_series_by_slug", side_effect=_slug_demo_only),
        ):
            res = self.client.get("/series/solo-leveling")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Solo Leveling", body)
        self.assertIn("Asura", body)
        self.assertIn("Open original site", body)
        self.assertIn("/app/add", body)

    def test_add_from_preview_manual_only_requires_title_when_missing(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("manualreq", "manualreq@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("manualreq@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", side_effect=lambda u: str(u).startswith("https://")):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "https://example.com/series/no-title",
                    "support_level": "manual_only",
                    "detection_source": "manual",
                },
            )
        self.assertEqual(res.status_code, 400)
        self.assertIn("title is required", (res.get_json() or {}).get("error", ""))

    def test_add_from_preview_rejects_unsafe_private_urls(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("unsafeurl", "unsafeurl@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("unsafeurl@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        with patch.object(app, "is_public_http_url", return_value=False):
            res = self.client.post(
                "/api/library/add-from-preview",
                json={
                    "source_url": "http://localhost/series/private",
                    "support_level": "extension_assisted",
                    "detection_source": "extension",
                    "title": "Nope",
                },
            )
        self.assertEqual(res.status_code, 400)
        self.assertIn("valid public http", (res.get_json() or {}).get("error", ""))

    def test_app_add_preview_uses_safe_dom_rendering(self):
        template_path = Path(app.app.root_path) / "templates" / "app_add.html"
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("document.getElementById(\"out\").replaceChildren(renderPreview(data));", content)
        self.assertIn("li.textContent = String(warning || \"\");", content)
        self.assertIn("title.textContent = data.canonical_title || data.title || \"Unknown title\";", content)
        self.assertIn("isSafeHttpUrl(data.cover_url || \"\")", content)
        self.assertIn("isSafeHttpUrl(data.source_url || \"\")", content)
        self.assertNotIn("out.innerHTML = renderPreview(data)", content)

    def test_discover_search_input_has_visible_label(self):
        res = self.client.get("/discover")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('label for="discover-unified-input"', body)
        self.assertIn("Search title or paste a source URL", body)

    def test_public_search_cover_img_has_alt_text(self):
        with app.app.test_request_context("/"):
            html = app.render_template(
                "public_search.html",
                q="x",
                results=[{"title": "Solo Leveling", "slug": "solo", "cover_url": "https://ex.com/c.jpg"}],
            )
        self.assertIn('alt="Solo Leveling cover"', html)
        self.assertIn('referrerpolicy="no-referrer"', html)

    def test_public_search_placeholder_renders_without_broken_img(self):
        with app.app.test_request_context("/"):
            html = app.render_template(
                "public_search.html",
                q="x",
                results=[{"title": "No Cover", "slug": "no-cover", "cover_url": ""}],
            )
        self.assertIn('class="search-card-cover" aria-hidden="true"', html)
        self.assertNotIn('<img class="search-card-cover"', html)

    def test_sources_page_hides_internal_script_names(self):
        rows = [
            {
                "id": "safe",
                "display_name": "Safe Source",
                "domains": ["safe.example"],
                "status": "working",
                "language": "en",
                "health": {},
                "nsfw": False,
            }
        ]
        with (
            patch.object(app.source_registry, "public_sources_with_health", return_value=rows),
            patch.object(app.source_registry, "aggregate_status_counts", return_value={"total": 1, "working": 1, "partial": 0, "broken": 0}),
            patch.object(app.source_registry, "load_health", return_value={}),
        ):
            res = self.client.get("/sources")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertNotIn("scripts/check_sources.py", body)

    def test_privacy_terms_dmca_pages_return_200(self):
        self.assertEqual(self.client.get("/privacy").status_code, 200)
        self.assertEqual(self.client.get("/terms").status_code, 200)
        self.assertEqual(self.client.get("/dmca").status_code, 200)

    def test_unknown_series_slug_shows_friendly_not_found(self):
        res = self.client.get("/series/slug-that-does-not-exist-anywhere")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Paste a URL", body)
        self.assertIn("No sources saved yet", body)

    def test_external_links_use_noopener_noreferrer(self):
        res = self.client.get("/discover?q=solo")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('target="_blank" rel="noopener noreferrer"', body)

    def test_check_get_route_is_friendly_and_does_not_404(self):
        res = self.client.get("/check", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/auth", res.headers.get("Location", ""))

    def test_check_get_logged_in_redirects_dashboard(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("checkuser", "checkuser@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("checkuser@example.com",)).fetchone()["id"])
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.get("/check", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/app", res.headers.get("Location", ""))

    def test_check_post_routes_remain_auth_protected(self):
        r1 = self.client.post("/check/1", follow_redirects=False)
        self.assertEqual(r1.status_code, 302)
        self.assertIn("/auth", r1.headers.get("Location", ""))
        r2 = self.client.post("/check-all", follow_redirects=False)
        self.assertEqual(r2.status_code, 302)
        self.assertIn("/auth", r2.headers.get("Location", ""))

    def test_sources_page_missing_health_shows_pending_and_unchecked(self):
        rows = [
            {
                "id": "safe",
                "display_name": "Safe Source",
                "domains": ["safe.example"],
                "status": "working",
                "language": "en",
                "health": {},
                "nsfw": False,
            }
        ]
        with (
            patch.object(app.source_registry, "public_sources_with_health", return_value=rows),
            patch.object(app.source_registry, "load_health", return_value={}),
        ):
            res = self.client.get("/sources")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("Health check pending", body)
        self.assertIn(">Unchecked<", body)
        self.assertIn(">—<", body)

    def test_landing_starter_picks_do_not_show_zero_sources_for_curated_titles(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertNotIn("One Piece</h3>\n            <p class=\"series-meta\">Manga · Latest ch. 1113 · 0 sources", body)
        self.assertNotIn("Jujutsu Kaisen</h3>\n            <p class=\"series-meta\">Manga · Latest ch. 271 · 0 sources", body)

    def test_discover_still_supports_title_search_and_url_paste(self):
        with patch.object(
            app,
            "source_engine_resolve_url",
            return_value=SourcePreview(
                source_name="Demo",
                source_url="https://example.com/series",
                support_level="manual_only",
                confidence=0.5,
                title="Demo",
            ),
        ):
            url_res = self.client.get("/discover?url=https%3A%2F%2Fexample.com%2Fseries")
        self.assertEqual(url_res.status_code, 200)
        self.assertIn("URL detection", url_res.get_data(as_text=True))
        title_res = self.client.get("/discover?q=Solo+Leveling")
        self.assertEqual(title_res.status_code, 200)
        self.assertIn("Results for", title_res.get_data(as_text=True))

    def test_demo_search_track_endpoints_renamed_and_legacy_disabled(self):
        legacy_search = self.client.get("/api/search?q=solo")
        self.assertEqual(legacy_search.status_code, 410)
        legacy_track = self.client.post("/api/track", json={"title": "Solo"})
        self.assertEqual(legacy_track.status_code, 410)
        demo_search = self.client.get("/api/demo/search?q=solo")
        self.assertEqual(demo_search.status_code, 410)
        self.assertFalse((demo_search.get_json() or {}).get("ok"))
        demo_track = self.client.post("/api/demo/track", json={"title": "Solo"})
        self.assertEqual(demo_track.status_code, 410)
        self.assertFalse((demo_track.get_json() or {}).get("ok"))

    def test_save_progress_normalizes_series_url_before_lookup(self):
        from werkzeug.security import generate_password_hash

        with app.get_conn() as conn:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                ("proguser", "proguser@example.com", generate_password_hash("secret12"), now),
            )
            uid = int(conn.execute("SELECT id FROM users WHERE email = ?", ("proguser@example.com",)).fetchone()["id"])
            conn.execute(
                "INSERT INTO bookmarks (user_id, title, url, story_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (uid, "Series", "https://example.com/series/demo", "story:demo", now),
            )
        with self.client.session_transaction() as sess:
            sess["user_id"] = uid
        res = self.client.post(
            "/api/progress",
            json={
                "series_url": "https://example.com/series/demo/",
                "chapter_num": 10,
                "chapter_label": "Ch. 10",
                "chapter_url": "https://example.com/series/demo/chapter-10",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue((res.get_json() or {}).get("ok"))

    def test_image_proxy_rejects_unknown_domain(self):
        res = self.client.get("/api/image-proxy?url=https%3A%2F%2Fevil.example%2Fx.jpg")
        self.assertEqual(res.status_code, 403)

    def test_image_proxy_rejects_private_or_non_https(self):
        r1 = self.client.get("/api/image-proxy?url=http%3A%2F%2Fuploads.mangadex.org%2Fx.jpg")
        self.assertEqual(r1.status_code, 400)
        r2 = self.client.get("/api/image-proxy?url=https%3A%2F%2Flocalhost%2Fx.jpg")
        self.assertIn(r2.status_code, {400, 403})

    def test_image_proxy_rejects_non_image_content_type(self):
        class _Resp:
            status_code = 200
            headers = {"Content-Type": "text/html"}

            def iter_content(self, chunk_size=65536):
                yield b"<html></html>"

            def close(self):
                return None

        with patch.object(app.SESSION, "get", return_value=_Resp()):
            res = self.client.get("/api/image-proxy?url=https%3A%2F%2Fuploads.mangadex.org%2Fcovers%2Fa%2Fb.jpg")
        self.assertEqual(res.status_code, 400)

    def test_image_proxy_allows_mangadex_image_host(self):
        class _Resp:
            status_code = 200
            headers = {"Content-Type": "image/jpeg"}

            def iter_content(self, chunk_size=65536):
                yield b"\xff\xd8\xff\xd9"

            def close(self):
                return None

        with patch.object(app.SESSION, "get", return_value=_Resp()):
            res = self.client.get("/api/image-proxy?url=https%3A%2F%2Fuploads.mangadex.org%2Fcovers%2Fa%2Fb.jpg")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Content-Type"), "image/jpeg")


if __name__ == "__main__":
    unittest.main()

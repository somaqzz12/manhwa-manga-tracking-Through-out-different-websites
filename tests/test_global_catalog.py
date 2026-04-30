"""Global series catalog: seed ingest, search, merge, private source links."""

from __future__ import annotations

import os
import tempfile
import unittest

import db as db_core
from services.global_catalog import repository as gc_repo
from services.global_catalog import search as catalog_search
from services import discovery
from services import metadata_discovery


class GlobalCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_path = db_core.DB_PATH
        self._prev_url = db_core.DATABASE_URL
        self._prev_pg = db_core.IS_POSTGRES
        fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_core.set_db_path(self._db_path)
        db_core.DATABASE_URL = ""
        db_core.IS_POSTGRES = False
        db_core.init_db()

    def tearDown(self) -> None:
        db_core.set_db_path(self._prev_path)
        db_core.DATABASE_URL = self._prev_url
        db_core.IS_POSTGRES = self._prev_pg
        try:
            os.unlink(self._db_path)
        except OSError:
            pass

    def test_ingest_provider_record_and_search(self) -> None:
        with db_core.get_conn() as conn:
            gc_repo.ingest_provider_record(
                conn,
                title="One Piece",
                canonical_title="One Piece",
                description="Pirates.",
                cover_url="https://example.com/cover.jpg",
                type_="manga",
                status="ongoing",
                year=1999,
                genres=["Adventure", "Shounen"],
                popularity_score=100.0,
                aliases=["OP"],
                external=("mangadex", "md-one-piece"),
                source_url="https://mangadex.org/title/md-one-piece",
                source_name="MangaDex",
                source_domain="mangadex.org",
                source_type="api",
                link_status="verified",
            )
        with db_core.get_conn() as conn:
            ids = gc_repo.search_series_ids(conn, "one piece", limit=10)
            self.assertTrue(ids)
            rows = catalog_search.discover_rows_from_catalog(conn, "onepiece", limit=5)
        titles = [r["title"] for r in rows]
        self.assertIn("One Piece", titles)

    def test_merge_external_id_dedupes(self) -> None:
        with db_core.get_conn() as conn:
            a = gc_repo.ingest_provider_record(
                conn,
                title="Merged Title A",
                canonical_title=None,
                description=None,
                cover_url=None,
                type_="manga",
                status="ongoing",
                year=None,
                genres=[],
                popularity_score=1.0,
                aliases=[],
                external=("anilist", "99"),
                source_url=None,
                source_name="",
                source_domain="",
                source_type="api",
                link_status="verified",
            )
            b = gc_repo.ingest_provider_record(
                conn,
                title="Merged Title A",
                canonical_title=None,
                description=None,
                cover_url=None,
                type_="manga",
                status="ongoing",
                year=None,
                genres=[],
                popularity_score=2.0,
                aliases=[],
                external=("anilist", "99"),
                source_url=None,
                source_name="",
                source_domain="",
                source_type="api",
                link_status="verified",
            )
        self.assertEqual(a, b)

    def test_extension_link_is_private(self) -> None:
        with db_core.get_conn() as conn:
            urow = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
            self.assertIsNotNone(urow)
            uid = int(urow["id"])
            sid = gc_repo.attach_extension_or_user_link(
                conn,
                user_id=uid,
                title="Extension Series",
                source_url="https://reader.example/series/x",
                source_name="Example",
                source_domain="reader.example",
            )
            row = conn.execute(
                "SELECT link_status, source_type, added_by_user_id FROM series_source_link WHERE series_id = ?",
                (sid,),
            ).fetchone()
        self.assertEqual(str(row["link_status"]), "private")
        self.assertEqual(str(row["source_type"]), "extension")
        self.assertEqual(int(row["added_by_user_id"]), uid)

    def test_manual_link_is_private(self) -> None:
        with db_core.get_conn() as conn:
            urow = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
            uid = int(urow["id"])
            sid = gc_repo.attach_manual_private_link(
                conn,
                user_id=uid,
                title="Manual Series",
                source_url="https://manual.example/manga/y",
                source_domain="manual.example",
            )
            row = conn.execute(
                "SELECT link_status, source_type FROM series_source_link WHERE series_id = ?",
                (sid,),
            ).fetchone()
        self.assertEqual(str(row["link_status"]), "private")
        self.assertEqual(str(row["source_type"]), "manual")

    def test_discover_search_no_demo_without_flag(self) -> None:
        with db_core.get_conn() as conn:
            gc_repo.ingest_provider_record(
                conn,
                title="Catalog Only",
                canonical_title=None,
                description=None,
                cover_url=None,
                type_="manga",
                status="ongoing",
                year=None,
                genres=[],
                popularity_score=5.0,
                aliases=[],
                external=None,
                source_url=None,
                source_name="",
                source_domain="",
                source_type="api",
                link_status="verified",
            )
        prev = db_core.DB_PATH
        try:
            db_core.set_db_path(self._db_path)
            out = metadata_discovery.discover_search("Catalog Only", live=False)
            self.assertFalse(out.get("is_demo"))
            self.assertTrue(any(r.get("title") == "Catalog Only" for r in out.get("results") or []))
        finally:
            db_core.set_db_path(prev)

    def test_get_series_by_id_from_db(self) -> None:
        with db_core.get_conn() as conn:
            sid = gc_repo.ingest_provider_record(
                conn,
                title="API Series",
                canonical_title=None,
                description="Hi",
                cover_url=None,
                type_="manga",
                status="ongoing",
                year=None,
                genres=["Action"],
                popularity_score=3.0,
                aliases=[],
                external=None,
                source_url="https://mangadex.org/title/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                source_name="MangaDex",
                source_domain="mangadex.org",
                source_type="api",
                link_status="verified",
            )
        prev = db_core.DB_PATH
        try:
            db_core.set_db_path(self._db_path)
            row = discovery.get_series_by_id(sid)
            self.assertIsNotNone(row)
            self.assertEqual(row.get("title"), "API Series")
            self.assertTrue(row.get("sources"))
        finally:
            db_core.set_db_path(prev)

from __future__ import annotations

import re
import secrets
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from typing import Optional

import config
from services import story_groups
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg2
    import psycopg2.extras
except Exception:
    psycopg2 = None
try:
    import psycopg
    from psycopg.rows import dict_row as psycopg_dict_row
except Exception:
    psycopg = None
    psycopg_dict_row = None

DB_PATH = config.DEFAULT_DB_PATH
DEFAULT_USER_EMAIL = config.DEFAULT_USER_EMAIL
DATABASE_URL = config.DATABASE_URL
IS_POSTGRES = config.IS_POSTGRES

DB_READY = False
DB_INIT_LOCK = threading.Lock()
log = logging.getLogger(__name__)


def set_db_path(path: str) -> None:
    global DB_PATH
    DB_PATH = path


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _adapt_query_for_postgres(query: str) -> str:
    adapted = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    if "?" in adapted:
        adapted = adapted.replace("?", "%s")
    if "INSERT OR IGNORE INTO" in query and "ON CONFLICT" not in adapted.upper():
        q = adapted.rstrip()
        if q.endswith(";"):
            q = q[:-1]
        adapted = q + " ON CONFLICT DO NOTHING"
    return adapted


class PostgresConn:
    def __init__(self) -> None:
        if psycopg2 is not None:
            self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
            self.driver = "psycopg2"
            return
        if psycopg is not None and psycopg_dict_row is not None:
            self.conn = psycopg.connect(DATABASE_URL, row_factory=psycopg_dict_row)
            self.driver = "psycopg3"
            return
        raise RuntimeError("No PostgreSQL driver installed. Install psycopg2-binary or psycopg[binary].")

    def execute(self, query: str, params=()):
        cur = self.conn.cursor()
        cur.execute(_adapt_query_for_postgres(query), params or ())
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _exc, _tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()
        return False


def get_conn():
    if IS_POSTGRES:
        return PostgresConn()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_bookmarks_has_global_unique_url(conn) -> bool:
    table_sql_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("bookmarks",),
    ).fetchone()
    table_sql = (table_sql_row["sql"] or "") if table_sql_row else ""
    if re.search(r"UNIQUE\s*\(\s*url\s*\)", table_sql, re.IGNORECASE):
        return True
    index_rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ?",
        ("bookmarks",),
    ).fetchall()
    for row in index_rows:
        sql = (row["sql"] or "").strip()
        if not sql:
            continue
        if re.search(r"UNIQUE\s+INDEX\s+.+\(\s*url\s*\)", sql, re.IGNORECASE):
            return True
    return False


def _migrate_sqlite_bookmarks_to_user_unique(conn) -> None:
    if not _sqlite_bookmarks_has_global_unique_url(conn):
        return
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookmarks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            latest_seen TEXT,
            latest_seen_num REAL,
            new_update INTEGER NOT NULL DEFAULT 0,
            last_checked TEXT,
            last_error TEXT,
            series_key TEXT,
            latest_seen_url TEXT,
            cover_url TEXT,
            latest_confidence REAL,
            latest_parser_version TEXT,
            latest_error_flags TEXT,
            story_id TEXT,
            UNIQUE(user_id, url)
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO bookmarks_new
        (id, user_id, title, url, latest_seen, latest_seen_num, new_update, last_checked, last_error, series_key, latest_seen_url, cover_url, latest_confidence, latest_parser_version, latest_error_flags, story_id)
        SELECT id, user_id, title, url, latest_seen, latest_seen_num, new_update, last_checked, last_error, series_key, latest_seen_url, cover_url, latest_confidence, latest_parser_version, latest_error_flags, NULL
        FROM bookmarks
        """
    )
    conn.execute("DROP TABLE bookmarks")
    conn.execute("ALTER TABLE bookmarks_new RENAME TO bookmarks")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_series_key ON bookmarks(series_key)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_user_url_unique ON bookmarks(user_id, url)")
    conn.execute("PRAGMA foreign_keys = ON")


def _ensure_bookmarks_story_id_column(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS story_id TEXT")
    else:
        cols = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        names = {c["name"] for c in cols}
        if "story_id" not in names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN story_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_story ON bookmarks(user_id, story_id)")


def _ensure_bookmarks_created_at_column(conn) -> None:
    now = _now_iso_z()
    if IS_POSTGRES:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS created_at TEXT")
        conn.execute(
            """
            UPDATE bookmarks
            SET created_at = COALESCE(NULLIF(created_at, ''), last_checked, ?)
            WHERE created_at IS NULL OR TRIM(created_at) = ''
            """,
            (now,),
        )
    else:
        cols = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        names = {c["name"] for c in cols}
        if "created_at" not in names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN created_at TEXT")
        conn.execute(
            """
            UPDATE bookmarks
            SET created_at = COALESCE(NULLIF(created_at, ''), last_checked, ?)
            WHERE created_at IS NULL OR TRIM(created_at) = ''
            """,
            (now,),
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_created_at ON bookmarks(created_at)")


def _ensure_bookmarks_metadata_columns(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS canonical_title TEXT")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS description TEXT")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS chapter_count INTEGER")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS source_name TEXT")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS source_domain TEXT")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS support_level TEXT")
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS detection_source TEXT")
        return
    cols = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
    names = {c["name"] for c in cols}
    if "canonical_title" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN canonical_title TEXT")
    if "description" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN description TEXT")
    if "chapter_count" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN chapter_count INTEGER")
    if "source_name" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN source_name TEXT")
    if "source_domain" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN source_domain TEXT")
    if "support_level" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN support_level TEXT")
    if "detection_source" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN detection_source TEXT")


def _ensure_users_integration_columns(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS rss_feed_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS webhook_url TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS api_access_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS public_list_slug TEXT")
        conn.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_email_chapters INTEGER NOT NULL DEFAULT 0"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_rss_feed ON users (rss_feed_token) WHERE rss_feed_token IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_tok ON users (api_access_token) WHERE api_access_token IS NOT NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_pub_slug ON users (public_list_slug) WHERE public_list_slug IS NOT NULL"
        )
        return
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(users)").fetchall()}
    add = [
        ("rss_feed_token", "TEXT"),
        ("webhook_url", "TEXT"),
        ("api_access_token", "TEXT"),
        ("public_list_slug", "TEXT"),
        ("notify_email_chapters", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for name, typ in add:
        if name not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {typ}")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_rss_feed ON users(rss_feed_token) WHERE rss_feed_token IS NOT NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_tok ON users(api_access_token) WHERE api_access_token IS NOT NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_pub_slug ON users(public_list_slug) WHERE public_list_slug IS NOT NULL"
    )


def _ensure_source_requests_table(conn) -> None:
    if IS_POSTGRES:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_requests (
                id BIGSERIAL PRIMARY KEY,
                domain TEXT NOT NULL,
                title_hint TEXT NOT NULL,
                url_example TEXT,
                created_at TEXT NOT NULL,
                votes INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            title_hint TEXT NOT NULL,
            url_example TEXT,
            created_at TEXT NOT NULL,
            votes INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def _ensure_normalized_library_tables(conn) -> None:
    if IS_POSTGRES:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series (
                id BIGSERIAL PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                norm_title_key TEXT NOT NULL,
                title TEXT NOT NULL,
                canonical_title TEXT,
                description TEXT,
                cover_url TEXT,
                type TEXT NOT NULL DEFAULT 'manga',
                status TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_norm_title_key ON series(norm_title_key)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_source (
                id BIGSERIAL PRIMARY KEY,
                series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                source_name TEXT,
                source_domain TEXT,
                source_url TEXT NOT NULL,
                normalized_source_url TEXT NOT NULL UNIQUE,
                support_level TEXT NOT NULL,
                source_policy TEXT NOT NULL,
                detection_source TEXT NOT NULL,
                latest_chapter TEXT,
                latest_chapter_url TEXT,
                chapter_count INTEGER,
                health_status TEXT NOT NULL DEFAULT 'unknown',
                last_checked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_series_id ON series_source(series_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library_item (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                preferred_source_id BIGINT REFERENCES series_source(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'active',
                notifications_enabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, series_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_library_item_user ON user_library_item(user_id)")
        _ensure_series_catalog_extensions(conn)
        return
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS series (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            norm_title_key TEXT NOT NULL,
            title TEXT NOT NULL,
            canonical_title TEXT,
            description TEXT,
            cover_url TEXT,
            type TEXT NOT NULL DEFAULT 'manga',
            status TEXT NOT NULL DEFAULT 'unknown',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_norm_title_key ON series(norm_title_key)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS series_source (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
            source_name TEXT,
            source_domain TEXT,
            source_url TEXT NOT NULL,
            normalized_source_url TEXT NOT NULL UNIQUE,
            support_level TEXT NOT NULL,
            source_policy TEXT NOT NULL,
            detection_source TEXT NOT NULL,
            latest_chapter TEXT,
            latest_chapter_url TEXT,
            chapter_count INTEGER,
            health_status TEXT NOT NULL DEFAULT 'unknown',
            last_checked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_series_id ON series_source(series_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_library_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
            preferred_source_id INTEGER REFERENCES series_source(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'active',
            notifications_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, series_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_library_item_user ON user_library_item(user_id)")
    _ensure_series_catalog_extensions(conn)


def _ensure_series_catalog_extensions(conn) -> None:
    """Global series catalog: extra columns on series + alias, external id, source link tables."""
    if IS_POSTGRES:
        conn.execute("ALTER TABLE series ADD COLUMN IF NOT EXISTS norm_compact TEXT")
        conn.execute("ALTER TABLE series ADD COLUMN IF NOT EXISTS year INTEGER")
        conn.execute("ALTER TABLE series ADD COLUMN IF NOT EXISTS genres_json TEXT")
        conn.execute("ALTER TABLE series ADD COLUMN IF NOT EXISTS popularity_score DOUBLE PRECISION NOT NULL DEFAULT 0")
        conn.execute(
            """
            UPDATE series SET norm_compact = lower(regexp_replace(norm_title_key, '\\s+', '', 'g'))
            WHERE norm_compact IS NULL OR norm_compact = ''
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_alias (
                id BIGSERIAL PRIMARY KEY,
                series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                alias_normalized TEXT NOT NULL,
                alias_display TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(series_id, alias_normalized)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_alias_norm ON series_alias(alias_normalized)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_external_id (
                id BIGSERIAL PRIMARY KEY,
                series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                external_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(provider, external_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_external_series ON series_external_id(series_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS series_source_link (
                id BIGSERIAL PRIMARY KEY,
                series_id BIGINT NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                source_name TEXT,
                source_domain TEXT,
                source_url TEXT NOT NULL,
                normalized_source_url TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL,
                link_status TEXT NOT NULL,
                confidence_score DOUBLE PRECISION,
                added_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
                last_seen_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_link_series ON series_source_link(series_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_link_status ON series_source_link(link_status)")
        return

    cols = {c["name"] for c in conn.execute("PRAGMA table_info(series)").fetchall()}
    for name, decl in (
        ("norm_compact", "TEXT"),
        ("year", "INTEGER"),
        ("genres_json", "TEXT"),
        ("popularity_score", "REAL NOT NULL DEFAULT 0"),
    ):
        if name not in cols:
            conn.execute(f"ALTER TABLE series ADD COLUMN {name} {decl}")
    conn.execute(
        """
        UPDATE series
        SET norm_compact = lower(replace(norm_title_key, ' ', ''))
        WHERE norm_compact IS NULL OR trim(norm_compact) = ''
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS series_alias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
            alias_normalized TEXT NOT NULL,
            alias_display TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(series_id, alias_normalized)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_alias_norm ON series_alias(alias_normalized)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS series_external_id (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(provider, external_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_external_series ON series_external_id(series_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS series_source_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
            source_name TEXT,
            source_domain TEXT,
            source_url TEXT NOT NULL,
            normalized_source_url TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL,
            link_status TEXT NOT NULL,
            confidence_score REAL,
            added_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            last_seen_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_link_series ON series_source_link(series_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_source_link_status ON series_source_link(link_status)")


def _ensure_bookmarks_last_synced_at(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS last_synced_at TEXT")
        return
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(bookmarks)").fetchall()}
    if "last_synced_at" not in cols:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN last_synced_at TEXT")


def _ensure_bookmarks_notes_column(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN IF NOT EXISTS notes TEXT")
        return
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(bookmarks)").fetchall()}
    if "notes" not in cols:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN notes TEXT")


def _ensure_user_library_item_progress_columns(conn) -> None:
    if IS_POSTGRES:
        conn.execute("ALTER TABLE user_library_item ADD COLUMN IF NOT EXISTS last_read_chapter TEXT")
        conn.execute("ALTER TABLE user_library_item ADD COLUMN IF NOT EXISTS last_synced_at TEXT")
        return
    cols = {c["name"] for c in conn.execute("PRAGMA table_info(user_library_item)").fetchall()}
    if "last_read_chapter" not in cols:
        conn.execute("ALTER TABLE user_library_item ADD COLUMN last_read_chapter TEXT")
    if "last_synced_at" not in cols:
        conn.execute("ALTER TABLE user_library_item ADD COLUMN last_synced_at TEXT")


def _backfill_bookmark_story_ids(conn) -> None:
    if IS_POSTGRES:
        rows = conn.execute(
            "SELECT id, series_key, story_id FROM bookmarks WHERE story_id IS NULL OR TRIM(COALESCE(story_id, '')) = ''"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, series_key, story_id FROM bookmarks WHERE story_id IS NULL OR IFNULL(TRIM(story_id), '') = ''"
        ).fetchall()
    for r in rows:
        sk = (r["series_key"] or "").strip()
        sid = story_groups.story_id_from_series_key(sk) if sk else story_groups.new_solo_story_id()
        conn.execute("UPDATE bookmarks SET story_id = ? WHERE id = ?", (sid, r["id"]))


def _bootstrap_default_user_password_hash() -> str:
    return generate_password_hash(secrets.token_hex(32))


def _harden_legacy_default_user_password(conn) -> None:
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE email = ?",
        (DEFAULT_USER_EMAIL,),
    ).fetchone()
    if not row:
        return
    try:
        ph = row["password_hash"]
        if ph and check_password_hash(ph, "local-only"):
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (_bootstrap_default_user_password_hash(), row["id"]),
            )
    except Exception:
        pass


def init_db() -> None:
    if IS_POSTGRES:
        with get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    latest_seen TEXT,
                    latest_seen_num DOUBLE PRECISION,
                    new_update INTEGER NOT NULL DEFAULT 0,
                    last_checked TEXT,
                    last_error TEXT,
                    series_key TEXT,
                    latest_seen_url TEXT,
                    cover_url TEXT,
                    latest_confidence DOUBLE PRECISION,
                    latest_parser_version TEXT,
                    latest_error_flags TEXT,
                    story_id TEXT,
                    created_at TEXT,
                    canonical_title TEXT,
                    description TEXT,
                    chapter_count INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reading_progress (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                    bookmark_id BIGINT REFERENCES bookmarks(id) ON DELETE CASCADE,
                    chapter_num DOUBLE PRECISION,
                    chapter_label TEXT,
                    source_url TEXT,
                    seen_at TEXT NOT NULL,
                    UNIQUE(bookmark_id, chapter_num, source_url)
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_series_key ON bookmarks(series_key)")
            conn.execute("ALTER TABLE bookmarks DROP CONSTRAINT IF EXISTS bookmarks_url_key")
            conn.execute("DROP INDEX IF EXISTS bookmarks_url_key")
            conn.execute("DROP INDEX IF EXISTS idx_bookmarks_url_unique")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_user_url_unique ON bookmarks(user_id, url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_url ON bookmarks(user_id, url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_progress_user_id ON reading_progress(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_progress_bookmark ON reading_progress(bookmark_id)")
            _ensure_bookmarks_story_id_column(conn)
            _ensure_bookmarks_created_at_column(conn)
            _ensure_bookmarks_metadata_columns(conn)
            _backfill_bookmark_story_ids(conn)

            now = _now_iso_z()
            conn.execute(
                "INSERT OR IGNORE INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USER_EMAIL, _bootstrap_default_user_password_hash(), now),
            )
            conn.execute(
                "UPDATE users SET username = COALESCE(username, split_part(email, '@', 1)) WHERE username IS NULL"
            )
            default_user = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USER_EMAIL,)).fetchone()
            default_user_id = default_user["id"]
            conn.execute("UPDATE bookmarks SET user_id = ? WHERE user_id IS NULL", (default_user_id,))
            conn.execute("UPDATE reading_progress SET user_id = ? WHERE user_id IS NULL", (default_user_id,))
            _harden_legacy_default_user_password(conn)
            _ensure_users_integration_columns(conn)
            _ensure_source_requests_table(conn)
            _ensure_normalized_library_tables(conn)
            _ensure_bookmarks_last_synced_at(conn)
            _ensure_bookmarks_notes_column(conn)
            _ensure_user_library_item_progress_columns(conn)
        return

    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        user_cols = conn.execute("PRAGMA table_info(users)").fetchall()
        user_col_names = {c["name"] for c in user_cols}
        if "username" not in user_col_names:
            conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                latest_seen TEXT,
                latest_seen_num REAL,
                new_update INTEGER NOT NULL DEFAULT 0,
                last_checked TEXT,
                last_error TEXT,
                created_at TEXT,
                canonical_title TEXT,
                description TEXT,
                chapter_count INTEGER
            )
            """
        )
        _migrate_sqlite_bookmarks_to_user_unique(conn)
        cols = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
        col_names = {c["name"] for c in cols}
        if "user_id" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN user_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id)")
        if "series_key" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN series_key TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_series_key ON bookmarks(series_key)")
        if "latest_seen_url" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN latest_seen_url TEXT")
        if "cover_url" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN cover_url TEXT")
        if "latest_confidence" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN latest_confidence REAL")
        if "latest_parser_version" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN latest_parser_version TEXT")
        if "latest_error_flags" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN latest_error_flags TEXT")
        if "story_id" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN story_id TEXT")
        if "created_at" not in col_names:
            conn.execute("ALTER TABLE bookmarks ADD COLUMN created_at TEXT")
        _ensure_bookmarks_metadata_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_url ON bookmarks(user_id, url)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_user_url_unique ON bookmarks(user_id, url)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_story ON bookmarks(user_id, story_id)")
        _ensure_bookmarks_created_at_column(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reading_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bookmark_id INTEGER NOT NULL,
                chapter_num REAL,
                chapter_label TEXT,
                source_url TEXT,
                seen_at TEXT NOT NULL,
                UNIQUE(bookmark_id, chapter_num, source_url),
                FOREIGN KEY(bookmark_id) REFERENCES bookmarks(id) ON DELETE CASCADE
            )
            """
        )
        progress_cols = conn.execute("PRAGMA table_info(reading_progress)").fetchall()
        progress_names = {c["name"] for c in progress_cols}
        if "user_id" not in progress_names:
            conn.execute("ALTER TABLE reading_progress ADD COLUMN user_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_progress_user_id ON reading_progress(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_progress_bookmark ON reading_progress(bookmark_id)")

        now = _now_iso_z()
        conn.execute(
            "INSERT OR IGNORE INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_EMAIL, _bootstrap_default_user_password_hash(), now),
        )
        conn.execute(
            "UPDATE users SET username = COALESCE(username, substr(email, 1, instr(email, '@') - 1)) WHERE username IS NULL"
        )
        default_user = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USER_EMAIL,)).fetchone()
        default_user_id = default_user["id"]
        conn.execute("UPDATE bookmarks SET user_id = ? WHERE user_id IS NULL", (default_user_id,))
        conn.execute(
            "UPDATE reading_progress SET user_id = ? WHERE user_id IS NULL",
            (default_user_id,),
        )
        _harden_legacy_default_user_password(conn)
        _backfill_bookmark_story_ids(conn)
        _ensure_users_integration_columns(conn)
        _ensure_source_requests_table(conn)
        _ensure_normalized_library_tables(conn)
        _ensure_bookmarks_last_synced_at(conn)
        _ensure_bookmarks_notes_column(conn)
        _ensure_user_library_item_progress_columns(conn)


def ensure_db_ready() -> None:
    global DB_READY
    if DB_READY:
        return
    with DB_INIT_LOCK:
        if DB_READY:
            return
        init_db()
        DB_READY = True


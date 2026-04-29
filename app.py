import math
import os
import re
import sqlite3
import json
import ipaddress
import logging
import secrets
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from services import chapter_parsing as chapter
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

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except Exception:
    webdriver = None
    Options = None

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

# Session cookies: HttpOnly always; SameSite default flips by environment so the
# Chrome extension (a chrome-extension:// origin) can still send the cookie back
# to us via cross-site fetch with credentials.
#   - In production (FLASK_DEBUG=0), Secure is required and SameSite must be "None"
#     for the extension to attach the cookie. Browsers will only honor SameSite=None
#     when the cookie is also Secure (HTTPS).
#   - In dev (FLASK_DEBUG=1), keep SameSite=Lax / not-Secure so localhost works.
# Override either with SESSION_COOKIE_SAMESITE / SESSION_COOKIE_SECURE env vars.
_IS_PROD = os.getenv("FLASK_DEBUG", "1") != "1"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv(
    "SESSION_COOKIE_SAMESITE", "None" if _IS_PROD else "Lax"
)
app.config["SESSION_COOKIE_SECURE"] = os.getenv(
    "SESSION_COOKIE_SECURE", "1" if _IS_PROD else "0"
) == "1"
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["WTF_CSRF_SSL_STRICT"] = os.getenv("FLASK_DEBUG", "1") != "1"
csrf = CSRFProtect(app)

_RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=_RATELIMIT_STORAGE_URI,
    default_limits=[],
    headers_enabled=True,
)


def _auth_username_key() -> str:
    # Per-username throttle (in addition to per-IP) to slow distributed credential stuffing.
    username = (request.form.get("username") or "").strip().lower()
    return f"auth-user:{username}" if username else f"auth-ip:{get_remote_address()}"


@app.errorhandler(429)
def _ratelimited(_err):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "rate limit exceeded"}), 429
    return render_template("auth.html", mode=(request.args.get("mode") or "login"), error="Too many attempts. Please wait a minute and try again."), 429

HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
MAX_CHECK_WORKERS = max(1, int(os.getenv("MAX_CHECK_WORKERS", "6")))
SCRAPE_RETRY_ON_FAIL = os.getenv("SCRAPE_RETRY_ON_FAIL", "0") == "1"
SCRAPE_TIMING_LOGS = os.getenv("SCRAPE_TIMING_LOGS", "0") == "1"
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "local@tracker")
MIN_PASSWORD_LENGTH = max(1, int(os.getenv("MIN_PASSWORD_LENGTH", "8")))
READ_PROGRESS_MAX_PER_BOOKMARK = int(os.getenv("READ_PROGRESS_MAX_PER_BOOKMARK", "400"))
INITIAL_AUTO_CHECK = os.getenv("INITIAL_AUTO_CHECK", "0") == "1"
CHECK_STALE_MINUTES = max(1, int(os.getenv("CHECK_STALE_MINUTES", "45")))
DEFAULT_BUG_REPORT_URL = "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues"
APP_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
DB_READY = False
DB_INIT_LOCK = threading.Lock()
CHECK_SINGLE_LOCKS: dict[int, threading.Lock] = {}
CHECK_SINGLE_LOCKS_GUARD = threading.Lock()
CHECK_ALL_LOCK = threading.Lock()
CHECK_ALL_STATUS_LOCK = threading.Lock()
CHECK_ALL_RUNNING = False
CHECK_ALL_LAST_FINISHED_AT: Optional[datetime] = None
SITE_CHECK_SEMAPHORES: dict[str, threading.Semaphore] = {}
SITE_CHECK_SEMAPHORES_GUARD = threading.Lock()
PER_SITE_CONCURRENCY = max(1, int(os.getenv("PER_SITE_CONCURRENCY", "2")))
_SCHEDULER = None
_SCHEDULER_LOCK = threading.Lock()
CHROME_EXTENSION_ID = os.getenv("CHROME_EXTENSION_ID", "").strip()
CORS_ALLOW_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
# Optional: allow the published extension origin without listing the full chrome-extension:// URL.
if CHROME_EXTENSION_ID:
    ext_origin = f"chrome-extension://{CHROME_EXTENSION_ID}"
    if ext_origin not in CORS_ALLOW_ORIGINS:
        CORS_ALLOW_ORIGINS.append(ext_origin)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
READ_PROGRESS_MAX_PER_USER = int(os.getenv("READ_PROGRESS_MAX_PER_USER", "20000"))
BOOKMARKS_PAGE_SIZE = max(1, int(os.getenv("BOOKMARKS_PAGE_SIZE", "60")))
SORT_MODES = frozenset({"added", "title", "updated", "unread"})
IMPORT_MAX_BYTES = int(os.getenv("IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
IMPORT_MAX_ITEMS = int(os.getenv("IMPORT_MAX_ITEMS", "20000"))
AUTH_RATE_LIMIT_PER_IP = os.getenv("AUTH_RATE_LIMIT_PER_IP", "10/minute;60/hour")
AUTH_RATE_LIMIT_PER_USER = os.getenv("AUTH_RATE_LIMIT_PER_USER", "8/minute;30/hour")
if not APP_DEBUG and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set in production")


_DEFAULT_GITHUB_URL = "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites"


@app.context_processor
def inject_template_globals():
    return {
        "bug_report_href": os.getenv("BUG_REPORT_URL", DEFAULT_BUG_REPORT_URL),
        "contact_email": os.getenv("CONTACT_EMAIL", "").strip(),
        "site_description": "Track manga and manhwa chapter releases, reading progress, and updates in one dashboard.",
        "min_password_length": MIN_PASSWORD_LENGTH,
        "github_url": (os.getenv("GITHUB_URL") or _DEFAULT_GITHUB_URL).strip(),
        "extension_coming_soon": True,
    }


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

SITE_PROFILES = {
    "asurascans.com": {"chapter_selector": "ul li a, .chapters a"},
    "mangakatana.com": {"chapter_selector": ".chapters a, .chapter-list a"},
    "arenascan.com": {"chapter_selector": ".wp-manga-chapter a, .listing-chapters_wrap a, a"},
    "mangadex.org": {"api": True},
}

DATABASE_URL = (os.getenv("DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
IS_POSTGRES = bool(DATABASE_URL)
ALLOW_SQLITE_IN_PRODUCTION = os.getenv("ALLOW_SQLITE_IN_PRODUCTION", "0") == "1"
if not APP_DEBUG and not IS_POSTGRES and not ALLOW_SQLITE_IN_PRODUCTION:
    raise RuntimeError(
        "Production requires DATABASE_URL (PostgreSQL) to prevent deploy-time data loss. "
        "Set ALLOW_SQLITE_IN_PRODUCTION=1 only if you accept ephemeral storage risk."
    )

if not APP_DEBUG and os.getenv("RATELIMIT_STORAGE_URI") is None:
    log.warning(
        "RATELIMIT_STORAGE_URI is not set; Flask-Limiter defaults to in-memory storage per process. "
        "With multiple workers (e.g. gunicorn) each process keeps its own counters, so limits look "
        "lenient or inconsistent. Set RATELIMIT_STORAGE_URI to a shared store such as "
        'redis://... on Railway, Render, etc.'
    )
if CORS_ALLOW_ORIGINS:
    if any(o.strip() in {"*", "https://*", "http://*"} or o.rstrip("/").endswith("/*") for o in CORS_ALLOW_ORIGINS):
        log.warning(
            "CORS_ALLOW_ORIGINS looks very broad. With Access-Control-Allow-Credentials enabled, "
            "only list exact origins that must send cookies (your extension or known web clients)."
        )
    else:
        log.info(
            "CORS credentials enabled for %d explicit origin(s); keep this list minimal and trusted.",
            len(CORS_ALLOW_ORIGINS),
        )
elif not APP_DEBUG:
    log.warning(
        "CORS_ALLOW_ORIGINS is empty in production. Browser extension requests send Origin: "
        "chrome-extension://<id>; without an explicit allowlist, those responses will not "
        "include Access-Control-Allow-Origin and API calls from the extension will fail CORS. "
        "Set CORS_ALLOW_ORIGINS to a comma-separated list including your app origin (e.g. "
        "https://app.example.com) and chrome-extension://<your-published-extension-id>."
    )


def _index_redirect_kwargs(
    q: Optional[str] = None, sort: Optional[str] = None, page: Optional[int] = None
) -> dict:
    qv = (q or "").strip()[:200]
    sv = (sort or "added").strip().lower()
    if sv not in SORT_MODES:
        sv = "added"
    kw = {}
    if qv:
        kw["q"] = qv
    if sv != "added":
        kw["sort"] = sv
    if page is not None and page > 1:
        kw["page"] = page
    return kw


def redirect_index_preserve_search():
    """After a dashboard POST, keep library `q`, `sort`, and `page` when the form submitted hidden fields."""
    try:
        page_val = max(1, int(request.form.get("page") or "1"))
    except ValueError:
        page_val = 1
    return redirect(
        url_for(
            "index",
            **_index_redirect_kwargs(request.form.get("q"), request.form.get("sort"), page_val),
        )
    )


def _bookmark_list_order_by(sort: str) -> str:
    if sort == "title":
        return "ORDER BY LOWER(b.title) ASC, b.id DESC"
    if sort == "updated":
        if IS_POSTGRES:
            return "ORDER BY b.last_checked DESC NULLS LAST, b.id DESC"
        return "ORDER BY (b.last_checked IS NULL), b.last_checked DESC, b.id DESC"
    if sort == "unread":
        return (
            "ORDER BY (CASE WHEN b.latest_seen_num IS NOT NULL AND rp.chapter_num IS NOT NULL "
            "THEN (b.latest_seen_num - rp.chapter_num) ELSE 0 END) DESC, b.id DESC"
        )
    return "ORDER BY b.id DESC"


def apply_manual_read_through(user_id: int, bookmark_id: int, chapter_num: float) -> None:
    """Insert reading progress for chapter_num and align bookmark latest_* / new_update like /api/progress."""
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, url, latest_seen, latest_seen_num, latest_seen_url
            FROM bookmarks
            WHERE id = ? AND user_id = ?
            """,
            (bookmark_id, user_id),
        ).fetchone()
        if not row:
            raise ValueError("bookmark not found")

    latest_n = row["latest_seen_num"]
    latest_lbl = (row["latest_seen"] or "").strip()
    latest_url = (row["latest_seen_url"] or "").strip()
    series_url = (row["url"] or "").strip()

    matches_latest = latest_n is not None and abs(float(latest_n) - float(chapter_num)) < 1e-6
    label = latest_lbl if matches_latest and latest_lbl else f"Ch {chapter_num:g}"
    src_url = (latest_url or series_url) if matches_latest else series_url

    upsert_progress(user_id, bookmark_id, chapter_num, label, src_url)

    with get_conn() as conn:
        cur = conn.execute(
            "SELECT latest_seen_num FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        ).fetchone()
        current_num = cur["latest_seen_num"] if cur else None
        if current_num is None or float(chapter_num) > float(current_num):
            conn.execute(
                """
                UPDATE bookmarks
                SET latest_seen = ?, latest_seen_num = ?, latest_seen_url = ?, last_checked = ?, last_error = NULL
                WHERE id = ? AND user_id = ?
                """,
                (label, chapter_num, src_url or None, now, bookmark_id, user_id),
            )
        cur2 = conn.execute(
            "SELECT latest_seen_num FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        ).fetchone()
        latest_after = cur2["latest_seen_num"] if cur2 else None
        if latest_after is not None and float(chapter_num) + 1e-6 >= float(latest_after):
            conn.execute(
                "UPDATE bookmarks SET new_update = 0 WHERE id = ? AND user_id = ?",
                (bookmark_id, user_id),
            )


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


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    allow_origin = False
    if CORS_ALLOW_ORIGINS:
        allow_origin = origin in CORS_ALLOW_ORIGINS
    elif APP_DEBUG:
        # Dev only: allow unpacked extensions and local dashboard tabs without a fixed allowlist.
        if origin.startswith("chrome-extension://"):
            allow_origin = True
        elif origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1"):
            allow_origin = True
    if allow_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        # Required so the browser surfaces the response when extension/dashboard
        # requests use credentials: "include" to forward the session cookie.
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Admin-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.before_request
def handle_preflight():
    ensure_db_ready()
    if request.method == "OPTIONS":
        return Response(status=204)
    return None


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
    # Legacy schema had global UNIQUE(url), which blocks the same series across users.
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
            UNIQUE(user_id, url)
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO bookmarks_new
        (id, user_id, title, url, latest_seen, latest_seen_num, new_update, last_checked, last_error, series_key, latest_seen_url, cover_url, latest_confidence, latest_parser_version, latest_error_flags)
        SELECT id, user_id, title, url, latest_seen, latest_seen_num, new_update, last_checked, last_error, series_key, latest_seen_url, cover_url, latest_confidence, latest_parser_version, latest_error_flags
        FROM bookmarks
        """
    )
    conn.execute("DROP TABLE bookmarks")
    conn.execute("ALTER TABLE bookmarks_new RENAME TO bookmarks")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_series_key ON bookmarks(series_key)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_user_url_unique ON bookmarks(user_id, url)")
    conn.execute("PRAGMA foreign_keys = ON")


def _bootstrap_default_user_password_hash() -> str:
    """Random password hash so the synthetic default user is not login-capable."""
    return generate_password_hash(secrets.token_hex(32))


def _harden_legacy_default_user_password(conn) -> None:
    """Replace the historical known password (username `local`, password `local-only`) if still stored."""
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
        log.exception("harden legacy default user password failed")


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
                    latest_error_flags TEXT
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

            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
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
                last_error TEXT
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bookmarks_user_url ON bookmarks(user_id, url)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookmarks_user_url_unique ON bookmarks(user_id, url)")

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

        # Ensure a default local user exists so extension flow keeps working.
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
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


def ensure_db_ready() -> None:
    global DB_READY
    if DB_READY:
        return
    with DB_INIT_LOCK:
        if DB_READY:
            return
        init_db()
        DB_READY = True


def parse_chapter_number(text: str) -> Optional[float]:
    return chapter.parse_chapter_number(text)


def parse_chapter_from_url(url: str) -> Optional[float]:
    return chapter.parse_chapter_from_url(url)


def is_valid_http_url(raw_url: str) -> bool:
    try:
        parsed = urlparse((raw_url or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def is_public_http_url(raw_url: str) -> bool:
    if not is_valid_http_url(raw_url):
        return False
    try:
        host = (urlparse((raw_url or "").strip()).hostname or "").strip()
        if not host:
            return False
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not infos:
            return False
        for info in infos:
            ip_txt = info[4][0]
            ip = ipaddress.ip_address(ip_txt)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def normalize_bookmark_url(raw_url: str) -> str:
    """Normalize URL for duplicate checks (trim, strip trailing slash, case-fold)."""
    return (raw_url or "").strip().rstrip("/").lower()


def _bookmark_title_search_clause(needle: str) -> tuple[str, list]:
    """Return (SQL fragment, params) to filter bookmarks by title substring (case-insensitive)."""
    n = (needle or "").strip()
    if not n:
        return "", []
    n = n[:200]
    n_lower = n.lower()
    if IS_POSTGRES:
        return " AND position(lower(?) in lower(b.title::text)) > 0", [n_lower]
    return " AND instr(lower(b.title), lower(?)) > 0", [n_lower]


def resolve_scrape_chapter_fields(
    label: Optional[str], num: Optional[float], latest_url: Optional[str]
) -> Optional[tuple[float, str, Optional[str]]]:
    """Return (chapter_num, display_label, chapter_url) only when a chapter number is known."""
    n = num
    if n is None and label:
        n = parse_chapter_number(label)
    if n is None and latest_url:
        n = parse_chapter_from_url(latest_url)
    if n is None:
        return None
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None
    disp = (label or "").strip()
    parsed_from_label = parse_chapter_number(disp) if disp else None
    if not disp or parsed_from_label is None:
        disp = f"Ch {int(n)}" if n.is_integer() else f"Ch {n}"
    return (n, disp, latest_url)


def get_default_user_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USER_EMAIL,)).fetchone()
    return int(row["id"])


def get_actor_user_id() -> int:
    user_id = session.get("user_id")
    if user_id:
        return int(user_id)
    return get_default_user_id()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        return conn.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required():
    return session.get("user_id") is not None


def api_session_user_id() -> Optional[int]:
    """Return the logged-in user id for extension JSON API routes.

    Never falls back to DEFAULT_USER_EMAIL — anonymous callers must not read or
    write another user's bookmarks or progress.
    """
    uid = session.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def admin_api_authorized() -> bool:
    """Gate destructive or scrape-proxy endpoints behind an explicit admin signal.

    Allows the request when any of these is true:
    - the caller is logged in (browser session), or
    - an ADMIN_API_TOKEN is configured and matches the X-Admin-Token header, or
    - the app is running with FLASK_DEBUG=1 (local development convenience).

    This intentionally does NOT treat "open API" env flags as a reason to expose
    scrape/maintenance tools without an admin signal.
    """
    if APP_DEBUG:
        return True
    if login_required():
        return True
    if ADMIN_API_TOKEN:
        provided = (request.headers.get("X-Admin-Token") or "").strip()
        if provided and provided == ADMIN_API_TOKEN:
            return True
    return False


def scrape_series_cover(url: str, series_title: str = "") -> Optional[str]:
    if not is_public_http_url(url):
        return None
    try:
        res = SESSION.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(res.text, "html.parser")
    meta_candidates = [
        ('meta[property="og:image"]', "content"),
        ('meta[name="og:image"]', "content"),
        ('meta[name="twitter:image"]', "content"),
        ('meta[property="twitter:image"]', "content"),
        ('link[rel="image_src"]', "href"),
    ]
    for selector, attr in meta_candidates:
        node = soup.select_one(selector)
        value = node.get(attr) if node else None
        if value:
            return urljoin(url, value.strip())

    title_tokens = {t for t in re.split(r"[^a-z0-9]+", (series_title or "").lower()) if len(t) >= 3}
    best_src: Optional[str] = None
    best_score = -10
    for img in soup.select("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        full_src = urljoin(url, src)
        hay = " ".join(
            [
                src.lower(),
                " ".join(img.get("class", [])) if img.get("class") else "",
                (img.get("alt") or "").lower(),
                (img.get("title") or "").lower(),
            ]
        )
        score = 0
        if re.search(r"cover|poster|thumb|thumbnail|wp-post-image|featured", hay, re.IGNORECASE):
            score += 4
        if re.search(r"logo|icon|avatar|banner|ads?|sprite", hay, re.IGNORECASE):
            score -= 5
        if title_tokens and any(token in hay for token in title_tokens):
            score += 3
        width = img.get("width")
        height = img.get("height")
        try:
            if width and int(width) >= 180:
                score += 1
            if height and int(height) >= 240:
                score += 1
        except Exception:
            pass
        if score > best_score:
            best_score = score
            best_src = full_src
    if best_src and best_score >= 0:
        return best_src
    return None


def resolve_series_listing_url(url: str) -> str:
    """Best-effort canonical series URL resolution for sites with chapter-style slugs."""
    if not is_public_http_url(url):
        return url
    parsed_slug = extract_series_slug(url)
    low = (url or "").lower()
    if parsed_slug and ("/manga/" in low or "/comics/" in low) and "chapter" not in low and not re.search(r"-\d+(?:\.\d+)?/?$", low):
        # Fast path: already looks like canonical series listing URL.
        return url.rstrip("/")
    try:
        res = SESSION.get(url, timeout=HTTP_TIMEOUT_SECONDS, allow_redirects=True)
        res.raise_for_status()
    except Exception:
        return url

    final_url = str(res.url or url).strip()
    soup = BeautifulSoup(res.text, "html.parser")
    candidates: list[str] = []
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        candidates.append(canonical.get("href", "").strip())
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get("content"):
        candidates.append(og_url.get("content", "").strip())
    candidates.append(final_url)
    candidates.append(url)

    def is_chapter_like(raw: str) -> bool:
        path = raw.lower()
        return bool(
            re.search(r"/(?:chapter|ch|episode|ep)[-_ /]?\d", path)
            or re.search(r"/c\d+(?:\.\d+)?(?:/|$)", path)
            or re.search(r"-chapter-\d+(?:\.\d+)?(?:/|$)", path)
            or re.search(r"-\d+(?:\.\d+)?/?$", path)
        )

    preferred = [c for c in candidates if "/manga/" in c.lower() or "/comics/" in c.lower()]
    if preferred:
        return preferred[0].rstrip("/")

    base_slug = extract_series_slug(url)
    if base_slug:
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            absolute = urljoin(final_url or url, href)
            lowered = absolute.lower()
            if "/manga/" not in lowered and "/comics/" not in lowered:
                continue
            href_slug = extract_series_slug(absolute)
            if href_slug and (href_slug == base_slug or base_slug in href_slug or href_slug in base_slug):
                return absolute.rstrip("/")

    for c in candidates:
        if c and not is_chapter_like(c):
            return c.rstrip("/")
    return final_url.rstrip("/") if final_url else url


def extract_series_slug(raw_url: str) -> str:
    return chapter.extract_series_slug(raw_url)


def iter_chapter_candidates(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str, str]]:
    return chapter.iter_chapter_candidates(soup, page_url)


def pick_best_candidate_with_debug(soup: BeautifulSoup, page_url: str) -> dict:
    return chapter.pick_best_candidate_with_debug(soup, page_url)


def pick_best_candidate(soup: BeautifulSoup, page_url: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    return chapter.pick_best_candidate(soup, page_url)


def get_profile_for_url(url: str) -> Optional[dict]:
    host = urlparse(url).netloc.lower().replace("www.", "")
    return SITE_PROFILES.get(host)


def scrape_with_profile(soup: BeautifulSoup, page_url: str, profile: dict) -> dict:
    selector = profile.get("chapter_selector")
    if not selector:
        return {"label": None, "chapter_num": None, "chapter_url": None, "confidence": 0.0, "parser_version": "profile-missing", "error_flags": ["missing_selector"]}

    page_slug = extract_series_slug(page_url)
    best = None
    for node in soup.select(selector):
        href = (node.get("href") or "").strip() if hasattr(node, "get") else ""
        if not href:
            continue
        absolute = urljoin(page_url, href)
        label = node.get_text(" ", strip=True)
        num = parse_chapter_number(label) or parse_chapter_from_url(absolute)
        if num is None:
            continue
        href_slug = extract_series_slug(absolute)
        if page_slug and href_slug and href_slug != page_slug and page_slug not in absolute.lower():
            continue
        score = int(num)
        if parse_chapter_from_url(absolute) is not None:
            score += 6
        if "chapter" in label.lower() or "episode" in label.lower():
            score += 2
        candidate = {"label": label, "chapter_num": num, "chapter_url": absolute, "score": score}
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best is None:
        return {"label": None, "chapter_num": None, "chapter_url": None, "confidence": 0.0, "parser_version": "profile-selector", "error_flags": ["profile_no_match"]}
    return {
        "label": best["label"],
        "chapter_num": best["chapter_num"],
        "chapter_url": best["chapter_url"],
        "confidence": 0.95,
        "parser_version": "profile-selector",
        "error_flags": [],
    }


def _log_scrape_timing(stage: str, url: str, started_at: float) -> None:
    if not SCRAPE_TIMING_LOGS:
        return
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    log.info("scrape_timing stage=%s elapsed_ms=%d url=%s", stage, elapsed_ms, url)


def _extract_mangadex_manga_id(url: str) -> tuple[Optional[str], Optional[str]]:
    raw = (url or "").strip()
    title_match = re.search(r"mangadex\.org/title/([0-9a-fA-F-]{36})", raw)
    if title_match:
        return title_match.group(1), None
    chapter_match = re.search(r"mangadex\.org/chapter/([0-9a-fA-F-]{36})", raw)
    if not chapter_match:
        return None, "MangaDex title/chapter id not found in URL"
    chapter_id = chapter_match.group(1)
    chapter_api_url = f"https://api.mangadex.org/chapter/{chapter_id}?includes[]=manga"
    t_fetch = time.perf_counter()
    try:
        res = SESSION.get(chapter_api_url, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
    except Exception as exc:
        _log_scrape_timing("mangadex_chapter_lookup_failed", chapter_api_url, t_fetch)
        return None, f"MangaDex chapter lookup failed: {exc}"
    _log_scrape_timing("mangadex_chapter_lookup", chapter_api_url, t_fetch)
    relationships = ((payload.get("data") or {}).get("relationships") or [])
    for rel in relationships:
        if (rel or {}).get("type") == "manga" and (rel or {}).get("id"):
            return rel["id"], None
    return None, "MangaDex chapter lookup returned no manga relationship"


def scrape_mangadex_api(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
    manga_id, id_err = _extract_mangadex_manga_id(url)
    if id_err or not manga_id:
        return None, None, None, id_err or "MangaDex manga id not found", {}
    api_url = (
        "https://api.mangadex.org/chapter"
        f"?manga={manga_id}"
        "&limit=1"
        "&order[chapter]=desc"
        "&translatedLanguage[]=en"
        "&contentRating[]=safe"
        "&contentRating[]=suggestive"
        "&contentRating[]=erotica"
        "&contentRating[]=pornographic"
    )
    t_fetch = time.perf_counter()
    try:
        res = SESSION.get(api_url, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
        payload = res.json()
    except Exception as exc:
        _log_scrape_timing("mangadex_api_fetch_failed", api_url, t_fetch)
        return None, None, None, f"MangaDex API failed: {exc}", {}
    _log_scrape_timing("mangadex_api_fetch", api_url, t_fetch)
    data = payload.get("data") or []
    if not data:
        return None, None, None, "MangaDex API returned no chapters", {"parser_version": "mangadex-api", "error_flags": ["no_chapter_candidates"]}
    first = data[0] or {}
    attrs = first.get("attributes") or {}
    chapter_raw = (attrs.get("chapter") or "").strip()
    title_raw = (attrs.get("title") or "").strip()
    chapter_num = None
    try:
        if chapter_raw:
            chapter_num = float(chapter_raw)
    except ValueError:
        chapter_num = parse_chapter_number(chapter_raw or title_raw)
    label = f"Ch {chapter_raw}" if chapter_raw else (title_raw or "Latest chapter")
    chapter_id = first.get("id")
    chapter_url = f"https://mangadex.org/chapter/{chapter_id}" if chapter_id else None
    info = {
        "label": label,
        "chapter_num": chapter_num,
        "chapter_url": chapter_url,
        "confidence": 0.99 if chapter_num is not None else 0.8,
        "parser_version": "mangadex-api",
        "error_flags": [],
    }
    return info["label"], info["chapter_num"], info["chapter_url"], None, info


def scrape_bs4(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
    if not is_public_http_url(url):
        return None, None, None, "Blocked URL (private/internal host)", {}
    profile = get_profile_for_url(url)
    if profile and profile.get("api") and "mangadex.org" in urlparse(url).netloc.lower():
        return scrape_mangadex_api(url)
    t_fetch = time.perf_counter()
    try:
        res = SESSION.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
    except Exception as exc:
        _log_scrape_timing("html_fetch_failed", url, t_fetch)
        return None, None, None, f"Request failed: {exc}", {}
    _log_scrape_timing("html_fetch", url, t_fetch)

    t_parse = time.perf_counter()
    soup = BeautifulSoup(res.text, "html.parser")
    _log_scrape_timing("html_parse", url, t_parse)
    t_extract = time.perf_counter()
    if profile and not profile.get("api"):
        info = scrape_with_profile(soup, url, profile)
        flags = set(info.get("error_flags") or [])
        if info.get("chapter_num") is None and flags.intersection({"profile_no_match", "missing_selector"}):
            # Site layout may have changed; generic parser often still works.
            fallback = pick_best_candidate_with_debug(soup, url)
            if fallback.get("chapter_num") is not None:
                fb_flags = list(fallback.get("error_flags") or [])
                fb_flags.append("profile_fallback_generic")
                fallback = {**fallback, "error_flags": fb_flags}
                info = fallback
            else:
                merged_flags = list(dict.fromkeys((info.get("error_flags") or []) + (fallback.get("error_flags") or [])))
                info = {
                    **info,
                    "error_flags": merged_flags,
                    "parser_version": info.get("parser_version", "") + "+tried-generic",
                }
    else:
        info = pick_best_candidate_with_debug(soup, url)
    _log_scrape_timing("chapter_extract", url, t_extract)
    return info.get("label"), info.get("chapter_num"), info.get("chapter_url"), None, info


def scrape_selenium(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
    if not is_public_http_url(url):
        return None, None, None, "Blocked URL (private/internal host)", {}
    if webdriver is None or Options is None:
        return None, None, None, "Selenium not available", {}

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        info = pick_best_candidate_with_debug(soup, url)
        return info.get("label"), info.get("chapter_num"), info.get("chapter_url"), None, info
    except Exception as exc:
        return None, None, None, f"Selenium failed: {exc}", {}
    finally:
        if driver:
            driver.quit()


def scrape_latest_update(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
    t_total = time.perf_counter()
    label, num, latest_url, err, info = scrape_bs4(url)
    if err is None:
        _log_scrape_timing("scrape_total_ok", url, t_total)
        return label, num, latest_url, None, info

    if os.getenv("USE_SELENIUM_FALLBACK", "1") == "1":
        t_selenium = time.perf_counter()
        s_label, s_num, s_latest_url, s_err, s_info = scrape_selenium(url)
        _log_scrape_timing("selenium_attempt", url, t_selenium)
        if s_err is None:
            _log_scrape_timing("scrape_total_ok_after_selenium", url, t_total)
            return s_label, s_num, s_latest_url, None, s_info
        return None, None, None, f"{err}; {s_err}", {}

    _log_scrape_timing("scrape_total_failed_no_selenium", url, t_total)
    return None, None, None, err, {}


def _get_site_check_semaphore(raw_url: str) -> threading.Semaphore:
    host = ""
    try:
        host = (urlparse(raw_url or "").hostname or "").lower()
    except Exception:
        host = ""
    if not host:
        host = "__unknown__"
    with SITE_CHECK_SEMAPHORES_GUARD:
        sem = SITE_CHECK_SEMAPHORES.get(host)
        if sem is None:
            sem = threading.Semaphore(PER_SITE_CONCURRENCY)
            SITE_CHECK_SEMAPHORES[host] = sem
        return sem


def _should_check_bookmark(last_checked: Optional[str], force: bool = False) -> bool:
    if force:
        return True
    if not last_checked:
        return True
    try:
        ts = datetime.fromisoformat(str(last_checked).replace("Z", "+00:00"))
    except Exception:
        return True
    age_seconds = (datetime.utcnow() - ts.replace(tzinfo=None)).total_seconds()
    return age_seconds >= CHECK_STALE_MINUTES * 60


def check_single(bookmark_id: int, user_id: int, force: bool = False) -> None:
    with CHECK_SINGLE_LOCKS_GUARD:
        lock = CHECK_SINGLE_LOCKS.setdefault(bookmark_id, threading.Lock())
    with lock:
        _check_single_locked(bookmark_id, user_id, force=force)


def _check_single_locked(bookmark_id: int, user_id: int, force: bool = False) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id)).fetchone()
        if not row:
            return
        if not _should_check_bookmark(row["last_checked"], force=force):
            return

        # Fast path: bookmarks are stored canonical at add/edit time. Re-resolving
        # every interval doubles request count and causes avoidable timeouts.
        effective_url = (row["url"] or "").strip()
        sem = _get_site_check_semaphore(effective_url)
        with sem:
            label, num, latest_url, err, debug_info = scrape_latest_update(effective_url)
            # Optional retry path for harder sites. Disabled by default to keep
            # regular checks fast and predictable under constrained hosting.
            if err and SCRAPE_RETRY_ON_FAIL:
                resolved_once = resolve_series_listing_url(effective_url)
                if resolved_once and resolved_once.rstrip("/") != effective_url.rstrip("/"):
                    label, num, latest_url, err, debug_info = scrape_latest_update(resolved_once)
                    if not err:
                        effective_url = resolved_once
        cover_url = row["cover_url"]
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        if err:
            conn.execute(
                "UPDATE bookmarks SET url = ?, last_checked = ?, last_error = ? WHERE id = ?",
                (effective_url or row["url"], now, err, bookmark_id),
            )
            if cover_url and cover_url != row["cover_url"]:
                conn.execute("UPDATE bookmarks SET cover_url = ? WHERE id = ?", (cover_url, bookmark_id))
            return

        resolved = resolve_scrape_chapter_fields(label, num, latest_url)
        latest_confidence = debug_info.get("confidence")
        latest_parser_version = debug_info.get("parser_version")
        latest_error_flags = ",".join(debug_info.get("error_flags", [])) if debug_info else None

        if resolved is None:
            # Scrape succeeded but we could not read a chapter — do not wipe good latest_* data.
            conn.execute(
                """
                UPDATE bookmarks
                SET url = ?, cover_url = ?, latest_confidence = ?, latest_parser_version = ?, latest_error_flags = ?,
                    last_checked = ?, last_error = NULL
                WHERE id = ?
                """,
                (
                    effective_url or row["url"],
                    cover_url,
                    latest_confidence,
                    latest_parser_version,
                    latest_error_flags,
                    now,
                    bookmark_id,
                ),
            )
            return

        num, label, latest_url = resolved
        previous_num = row["latest_seen_num"]
        new_update = 0

        if num is not None and previous_num is not None:
            new_update = 1 if num > previous_num else 0
        elif label and row["latest_seen"]:
            new_update = 1 if str(label).strip() != str(row["latest_seen"]).strip() else 0
        if row["latest_seen"] is None:
            new_update = 0

        conn.execute(
            """
            UPDATE bookmarks
            SET url = ?, latest_seen = ?, latest_seen_num = ?, latest_seen_url = ?, cover_url = ?, latest_confidence = ?, latest_parser_version = ?, latest_error_flags = ?, new_update = ?, last_checked = ?, last_error = NULL
            WHERE id = ?
            """,
            (
                effective_url or row["url"],
                label,
                num,
                latest_url,
                cover_url,
                latest_confidence,
                latest_parser_version,
                latest_error_flags,
                new_update,
                now,
                bookmark_id,
            ),
        )


def upsert_progress(user_id: int, bookmark_id: int, chapter_num: Optional[float], chapter_label: str, source_url: str) -> None:
    if chapter_num is None:
        chapter_num = parse_chapter_number(chapter_label) or parse_chapter_from_url(source_url)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO reading_progress (user_id, bookmark_id, chapter_num, chapter_label, source_url, seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, bookmark_id, chapter_num, chapter_label, source_url, now),
        )
    maybe_prune_reading_progress(user_id, bookmark_id)


def maybe_prune_reading_progress(user_id: int, bookmark_id: int) -> None:
    max_keep = READ_PROGRESS_MAX_PER_BOOKMARK
    if max_keep <= 0:
        return
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM reading_progress WHERE user_id = ? AND bookmark_id = ?",
            (user_id, bookmark_id),
        ).fetchone()
        total = int(row["c"] or 0) if row else 0
        excess = total - max_keep
        if excess <= 0:
            return
        old_rows = conn.execute(
            "SELECT id FROM reading_progress WHERE user_id = ? AND bookmark_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, bookmark_id, excess),
        ).fetchall()
        for r in old_rows:
            conn.execute("DELETE FROM reading_progress WHERE id = ?", (r["id"],))


def maybe_prune_reading_progress_for_user(user_id: int) -> int:
    """Trim a user's total reading_progress rows down to READ_PROGRESS_MAX_PER_USER.

    A noisy importer or a runaway extension on one user shouldn't bloat the shared
    database for everyone else. Returns the number of rows deleted.
    """
    max_keep = READ_PROGRESS_MAX_PER_USER
    if max_keep <= 0:
        return 0
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM reading_progress WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total = int(row["c"] or 0) if row else 0
        excess = total - max_keep
        if excess <= 0:
            return 0
        old_rows = conn.execute(
            "SELECT id FROM reading_progress WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, excess),
        ).fetchall()
        for r in old_rows:
            conn.execute("DELETE FROM reading_progress WHERE id = ?", (r["id"],))
    return excess


def prune_reading_progress_all_users() -> None:
    """Background sweep so any user above the per-user cap is trimmed periodically."""
    if READ_PROGRESS_MAX_PER_USER <= 0:
        return
    try:
        ensure_db_ready()
        with get_conn() as conn:
            users = conn.execute(
                "SELECT user_id, COUNT(*) AS c FROM reading_progress WHERE user_id IS NOT NULL GROUP BY user_id"
            ).fetchall()
        for u in users:
            if int(u["c"] or 0) > READ_PROGRESS_MAX_PER_USER:
                deleted = maybe_prune_reading_progress_for_user(int(u["user_id"]))
                if deleted:
                    log.info("pruned %d reading_progress rows for user %s", deleted, u["user_id"])
    except Exception:
        log.exception("prune_reading_progress_all_users failed")


def check_all(user_id: int, force: bool = False) -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, last_checked FROM bookmarks WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    ids = [
        row["id"]
        for row in rows
        if _should_check_bookmark(row["last_checked"], force=force)
    ]
    if not ids:
        return
    # Parallel checks significantly reduce total refresh latency.
    with ThreadPoolExecutor(max_workers=min(MAX_CHECK_WORKERS, len(ids))) as pool:
        futures = [pool.submit(check_single, bid, user_id, force) for bid in ids]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                log.exception("check_single failed in batch check")


def check_all_safe(user_id: int, force: bool = False) -> bool:
    """Run check_all only when no other check-all run is active."""
    acquired = CHECK_ALL_LOCK.acquire(blocking=False)
    if not acquired:
        return False
    try:
        check_all(user_id, force=force)
        return True
    finally:
        CHECK_ALL_LOCK.release()


def _format_relative_age(ts: Optional[datetime]) -> str:
    if ts is None:
        return "never"
    try:
        seconds = max(0, int((datetime.utcnow() - ts).total_seconds()))
    except Exception:
        return "unknown"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def check_all_users() -> None:
    ensure_db_ready()
    with get_conn() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    for user in users:
        check_all(int(user["id"]), force=False)


@app.route("/auth", methods=["GET", "POST"])
@limiter.limit(
    AUTH_RATE_LIMIT_PER_IP,
    methods=["POST"],
    key_func=get_remote_address,
)
@limiter.limit(
    AUTH_RATE_LIMIT_PER_USER,
    methods=["POST"],
    key_func=_auth_username_key,
)
def auth_page():
    mode = (request.args.get("mode") or "login").strip().lower()
    error = None
    if request.method == "POST":
        try:
            action = request.form.get("action", "login")
            username = (request.form.get("username") or "").strip().lower()
            password = request.form.get("password") or ""
            if not username or not password:
                error = "Username and password are required."
            elif action == "register" and len(password) < MIN_PASSWORD_LENGTH:
                error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            elif action == "register":
                with get_conn() as conn:
                    exists_username = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                    if exists_username:
                        error = "Username already exists."
                    else:
                        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                        synthetic_email = f"{username}@local.user"
                        insert_cur = conn.execute(
                            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                            (username, synthetic_email, generate_password_hash(password), now),
                        )
                        # PostgreSQL drivers do not set lastrowid; fetch the row we just inserted.
                        if IS_POSTGRES:
                            inserted = conn.execute(
                                "SELECT id FROM users WHERE username = ? AND email = ?",
                                (username, synthetic_email),
                            ).fetchone()
                            if not inserted:
                                raise RuntimeError("user insert did not return id")
                            new_user_id = int(inserted["id"])
                        else:
                            new_user_id = int(insert_cur.lastrowid)
                        # Drop any pre-auth session state so the post-auth cookie cannot
                        # carry attacker-controlled values from a fixated session.
                        session.clear()
                        session["user_id"] = new_user_id
                        return redirect(url_for("index"))
            else:
                with get_conn() as conn:
                    user = conn.execute(
                        "SELECT * FROM users WHERE username = ?",
                        (username,),
                    ).fetchone()
                if user is None or not check_password_hash(user["password_hash"], password):
                    error = "Invalid username or password."
                else:
                    session.clear()
                    session["user_id"] = int(user["id"])
                    return redirect(url_for("index"))
        except Exception:
            error = "Temporary database issue. Please try again in a few seconds."

    return render_template("auth.html", mode=mode, error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("auth_page"))


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "status": "healthy"})


@app.route("/")
def home():
    if not login_required():
        return render_template("landing.html")
    return redirect(url_for("index"))


@app.route("/dashboard")
def index():
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        # Session can become stale after deploys or DB resets.
        session.pop("user_id", None)
        return redirect(url_for("auth_page"))

    page_size = BOOKMARKS_PAGE_SIZE
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    search_q = (request.args.get("q") or "").strip()[:200]
    sort = (request.args.get("sort") or "added").strip().lower()
    if sort not in SORT_MODES:
        sort = "added"
    title_clause, title_params = _bookmark_title_search_clause(search_q)
    order_clause = _bookmark_list_order_by(sort)
    index_link_kw = _index_redirect_kwargs(search_q, sort)
    edit_link_kw = _index_redirect_kwargs(search_q, sort, page)

    with get_conn() as conn:
        # Library-wide aggregates (computed across all pages so the summary stays accurate).
        agg_rows = conn.execute(
            """
            SELECT b.latest_seen_num AS latest_num,
                   rp.chapter_num AS read_num
            FROM bookmarks b
            LEFT JOIN (
                SELECT x.bookmark_id, x.chapter_num
                FROM reading_progress x
                INNER JOIN (
                    SELECT bookmark_id, MAX(id) AS max_id
                    FROM reading_progress
                    WHERE user_id = ?
                    GROUP BY bookmark_id
                ) y ON y.bookmark_id = x.bookmark_id AND y.max_id = x.id
                WHERE x.user_id = ?
            ) rp ON rp.bookmark_id = b.id
            WHERE b.user_id = ?
            """,
            (user_id, user_id, user_id),
        ).fetchall()

        if title_clause:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM bookmarks b WHERE b.user_id = ?{title_clause}",
                (user_id, *title_params),
            ).fetchone()
            total_count = int(count_row["c"] or 0) if count_row else 0
        else:
            total_count = len(agg_rows)

        total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count else 1
        if page > total_pages:
            page = total_pages
        offset = (page - 1) * page_size

        rows = conn.execute(
            f"""
            SELECT b.*,
                   rp.chapter_num AS read_chapter_num,
                   rp.chapter_label AS read_chapter_label,
                   rp.source_url AS read_source_url
            FROM bookmarks b
            LEFT JOIN (
                SELECT x.bookmark_id, x.chapter_num, x.chapter_label, x.source_url
                FROM reading_progress x
                INNER JOIN (
                    SELECT bookmark_id, MAX(id) AS max_id
                    FROM reading_progress
                    WHERE user_id = ?
                    GROUP BY bookmark_id
                ) y ON y.bookmark_id = x.bookmark_id AND y.max_id = x.id
                WHERE x.user_id = ?
            ) rp ON rp.bookmark_id = b.id
            WHERE b.user_id = ?
            {title_clause}
            {order_clause}
            LIMIT ? OFFSET ?
            """,
            (user_id, user_id, user_id, *title_params, page_size, offset),
        ).fetchall()

    total_unread = 0.0
    behind_count = 0
    for agg in agg_rows:
        latest_num = agg["latest_num"]
        read_num = agg["read_num"]
        if latest_num is None or read_num is None:
            continue
        try:
            diff = float(latest_num) - float(read_num)
        except (TypeError, ValueError):
            continue
        if diff > 0:
            total_unread += diff
            behind_count += 1

    bookmarks = []
    for row in rows:
        item = dict(row)
        latest_num = item.get("latest_seen_num")
        read_num = item.get("read_chapter_num")
        unread = 0.0
        if latest_num is not None and read_num is not None:
            try:
                unread = max(0.0, float(latest_num) - float(read_num))
            except Exception:
                unread = 0.0
        item["unread_count"] = unread
        # Continue = resume where you left off (last-read chapter URL from progress),
        # not the site's newest chapter (latest_seen_url), which skips the story ahead.
        item["continue_url"] = item.get("read_source_url") or item.get("url")
        bookmarks.append(item)

    with CHECK_ALL_STATUS_LOCK:
        check_all_running = CHECK_ALL_RUNNING
        check_all_last_finished_at = CHECK_ALL_LAST_FINISHED_AT
    check_all_status_text = (
        "Check running..."
        if check_all_running
        else f"Last checked: {_format_relative_age(check_all_last_finished_at)}"
    )

    return render_template(
        "index.html",
        bookmarks=bookmarks,
        current_user=current_user,
        total_unread=int(total_unread) if total_unread.is_integer() else round(total_unread, 1),
        behind_count=behind_count,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        page_size=page_size,
        search_q=search_q,
        sort=sort,
        index_link_kw=index_link_kw,
        edit_link_kw=edit_link_kw,
        check_all_running=check_all_running,
        check_all_status_text=check_all_status_text,
    )


@app.route("/export", methods=["GET"])
def export_data():
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        bookmarks = conn.execute("SELECT * FROM bookmarks WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        progress = conn.execute("SELECT * FROM reading_progress WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
    payload = {
        "version": 1,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "bookmarks": [dict(b) for b in bookmarks],
        "reading_progress": [dict(p) for p in progress],
    }
    body = json.dumps(payload, ensure_ascii=True, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="manga-watchlist-backup.json"'},
    )


@app.route("/import", methods=["POST"])
def import_data():
    if not login_required():
        return redirect(url_for("auth_page"))
    file = request.files.get("backup_file")
    if file is None or not (file.filename or "").strip():
        flash("No backup file selected. Choose a Manga Watchlist backup JSON to import.", "warning")
        return redirect_index_preserve_search()

    raw = file.read(IMPORT_MAX_BYTES + 1)
    if len(raw) == 0:
        flash("Import failed: the file is empty.", "error")
        return redirect_index_preserve_search()
    if len(raw) > IMPORT_MAX_BYTES:
        max_mb = IMPORT_MAX_BYTES / (1024 * 1024)
        flash(f"Import failed: file is larger than {max_mb:.1f} MB. Trim it or split it before importing.", "error")
        return redirect_index_preserve_search()

    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        flash("Import failed: file is not UTF-8 text. Export a fresh backup and try again.", "error")
        return redirect_index_preserve_search()
    except json.JSONDecodeError:
        flash("Import failed: file is not valid JSON. Did you select the right file?", "error")
        return redirect_index_preserve_search()

    if not isinstance(payload, dict):
        flash("Import failed: backup file is missing the expected structure.", "error")
        return redirect_index_preserve_search()

    bookmarks = payload.get("bookmarks")
    progress = payload.get("reading_progress")
    if bookmarks is None and progress is None:
        flash("Import failed: backup has no \"bookmarks\" or \"reading_progress\" sections.", "error")
        return redirect_index_preserve_search()

    if bookmarks is not None and not isinstance(bookmarks, list):
        flash("Import failed: \"bookmarks\" must be a list.", "error")
        return redirect_index_preserve_search()
    if progress is not None and not isinstance(progress, list):
        flash("Import failed: \"reading_progress\" must be a list.", "error")
        return redirect_index_preserve_search()

    bookmarks = bookmarks or []
    progress = progress or []

    if len(bookmarks) + len(progress) > IMPORT_MAX_ITEMS:
        flash(
            f"Import failed: backup has {len(bookmarks) + len(progress)} entries which exceeds the {IMPORT_MAX_ITEMS} item limit.",
            "error",
        )
        return redirect_index_preserve_search()

    user_id = get_actor_user_id()
    id_map: dict[int, int] = {}
    inserted_bookmarks = 0
    skipped_invalid_bookmarks = 0
    skipped_malformed_bookmarks = 0
    inserted_progress = 0
    skipped_progress = 0
    skipped_malformed_progress = 0
    with get_conn() as conn:
        for b in bookmarks:
            if not isinstance(b, dict):
                skipped_malformed_bookmarks += 1
                continue
            old_id = int(b.get("id") or 0)
            raw_url = (b.get("url") or "").strip()
            title = (b.get("title") or "").strip()
            if not title or not is_public_http_url(raw_url):
                skipped_invalid_bookmarks += 1
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO bookmarks
                (user_id, title, url, latest_seen, latest_seen_num, latest_seen_url, cover_url, new_update, last_checked, last_error, series_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    title,
                    raw_url,
                    b.get("latest_seen"),
                    b.get("latest_seen_num"),
                    b.get("latest_seen_url"),
                    b.get("cover_url"),
                    b.get("new_update", 0),
                    b.get("last_checked"),
                    b.get("last_error"),
                    b.get("series_key"),
                ),
            )
            if getattr(cur, "rowcount", 0) == 1:
                inserted_bookmarks += 1
            new_row = conn.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, raw_url),
            ).fetchone()
            if old_id and new_row:
                id_map[old_id] = int(new_row["id"])
        for p in progress:
            if not isinstance(p, dict):
                skipped_malformed_progress += 1
                continue
            mapped_bookmark_id = id_map.get(int(p.get("bookmark_id") or 0))
            if mapped_bookmark_id is None:
                skipped_progress += 1
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO reading_progress
                (user_id, bookmark_id, chapter_num, chapter_label, source_url, seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    mapped_bookmark_id,
                    p.get("chapter_num"),
                    p.get("chapter_label"),
                    p.get("source_url"),
                    p.get("seen_at") or datetime.utcnow().isoformat(timespec="seconds") + "Z",
                ),
            )
            if getattr(cur, "rowcount", 0) == 1:
                inserted_progress += 1

    pruned = maybe_prune_reading_progress_for_user(user_id)

    parts = [
        f"Import finished. Added {inserted_bookmarks} series and {inserted_progress} reading progress rows."
    ]
    skipped_total = (
        skipped_invalid_bookmarks
        + skipped_malformed_bookmarks
        + skipped_progress
        + skipped_malformed_progress
    )
    if skipped_invalid_bookmarks:
        parts.append(f"Skipped {skipped_invalid_bookmarks} series (missing title or invalid URL).")
    if skipped_malformed_bookmarks:
        parts.append(f"Skipped {skipped_malformed_bookmarks} malformed series entries.")
    if skipped_progress:
        parts.append(f"Skipped {skipped_progress} progress rows (no matching series).")
    if skipped_malformed_progress:
        parts.append(f"Skipped {skipped_malformed_progress} malformed progress entries.")
    if pruned:
        parts.append(f"Trimmed {pruned} oldest progress rows to stay under the per-user cap.")
    flash(" ".join(parts), "warning" if skipped_total else "success")
    return redirect_index_preserve_search()


@app.route("/add", methods=["POST"])
def add_bookmark():
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    if not title or not is_public_http_url(url):
        return redirect_index_preserve_search()

    bookmark_id: Optional[int] = None
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO bookmarks (user_id, title, url, cover_url) VALUES (?, ?, ?, ?)",
            (user_id, title, url, None),
        )
        row = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND url = ?",
            (user_id, url),
        ).fetchone()
        if row:
            bookmark_id = int(row["id"])

    if bookmark_id is not None:
        bid, uid = bookmark_id, user_id

        def _check_after_add():
            try:
                check_single(bid, uid, force=True)
            except Exception:
                log.exception("check_single after add_bookmark failed")

        threading.Thread(target=_check_after_add, name=f"check-after-add-{bid}", daemon=True).start()

    return redirect_index_preserve_search()


@app.route("/check/<int:bookmark_id>", methods=["POST"])
def check_bookmark(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    check_single(bookmark_id, get_actor_user_id(), force=True)
    return redirect_index_preserve_search()


@app.route("/check-all", methods=["POST"])
def check_all_route():
    if not login_required():
        return redirect(url_for("auth_page"))
    if CHECK_ALL_LOCK.locked():
        return redirect_index_preserve_search()
    force = (request.form.get("force") or "").strip() == "1"
    user_id = get_actor_user_id()

    def _run_check_all():
        global CHECK_ALL_RUNNING, CHECK_ALL_LAST_FINISHED_AT
        with CHECK_ALL_STATUS_LOCK:
            CHECK_ALL_RUNNING = True
        ran = False
        try:
            ran = check_all_safe(user_id, force=force)
            if not ran:
                log.info("check_all already running; skipped duplicate start")
        finally:
            with CHECK_ALL_STATUS_LOCK:
                CHECK_ALL_RUNNING = False
                if ran:
                    CHECK_ALL_LAST_FINISHED_AT = datetime.utcnow()

    threading.Thread(
        target=_run_check_all,
        name=f"check-all-user-{user_id}",
        daemon=True,
    ).start()
    return redirect_index_preserve_search()


@app.route("/api/check-all/status", methods=["GET"])
def check_all_status_api():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    with CHECK_ALL_STATUS_LOCK:
        running = CHECK_ALL_RUNNING
        finished_at = CHECK_ALL_LAST_FINISHED_AT.isoformat(timespec="seconds") + "Z" if CHECK_ALL_LAST_FINISHED_AT else None
    return jsonify({"ok": True, "running": running, "finished_at": finished_at})


@app.route("/mark-seen/<int:bookmark_id>", methods=["POST"])
def mark_seen(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("UPDATE bookmarks SET new_update = 0 WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect_index_preserve_search()


@app.route("/mark-all-seen", methods=["POST"])
def mark_all_seen():
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("UPDATE bookmarks SET new_update = 0 WHERE user_id = ?", (user_id,))
    flash("Marked all series as seen — new-update flags cleared for your whole library.", "success")
    return redirect_index_preserve_search()


@app.route("/bookmark/<int:bookmark_id>/read-through", methods=["POST"])
def read_through(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    raw = (request.form.get("chapter_num") or "").strip()
    try:
        chapter_num = float(raw)
    except ValueError:
        flash("Enter a valid chapter number.", "error")
        return redirect_index_preserve_search()
    if not math.isfinite(chapter_num) or chapter_num < 0:
        flash("Chapter number must be zero or positive.", "error")
        return redirect_index_preserve_search()
    try:
        apply_manual_read_through(user_id, bookmark_id, chapter_num)
    except ValueError:
        flash("Series not found.", "error")
        return redirect_index_preserve_search()
    flash("Reading progress updated.", "success")
    return redirect_index_preserve_search()


@app.route("/bookmark/<int:bookmark_id>/edit", methods=["GET", "POST"])
def edit_bookmark(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    if request.method == "POST":
        return_q = (request.form.get("q") or "").strip()[:200]
        return_sort = (request.form.get("sort") or "").strip().lower()
    else:
        return_q = (request.args.get("q") or "").strip()[:200]
        return_sort = (request.args.get("sort") or "").strip().lower()
    if return_sort not in SORT_MODES:
        return_sort = "added"
    try:
        rp = request.form.get("page") if request.method == "POST" else request.args.get("page")
        return_page = max(1, int(rp or "1"))
    except ValueError:
        return_page = 1
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, url FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        ).fetchone()
    if not row:
        flash("Series not found.", "error")
        return redirect(url_for("index", **_index_redirect_kwargs(return_q, return_sort, return_page)))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        url = request.form.get("url", "").strip()
        if not title or not is_public_http_url(url):
            flash("Title and a valid http(s) URL are required.", "error")
            return render_template(
                "edit_bookmark.html",
                bookmark=dict(row),
                return_q=return_q,
                return_sort=return_sort,
                return_page=return_page,
                edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
            )
        old_url = (row["url"] or "").strip()
        new_url = url.strip()
        norm_new = normalize_bookmark_url(new_url)
        url_changed = new_url.rstrip("/") != old_url.rstrip("/")
        with get_conn() as conn:
            others = conn.execute(
                "SELECT url FROM bookmarks WHERE user_id = ? AND id != ?",
                (user_id, bookmark_id),
            ).fetchall()
            if any(normalize_bookmark_url(o["url"]) == norm_new for o in others):
                flash("That series URL is already in your library.", "error")
                return render_template(
                    "edit_bookmark.html",
                    bookmark=dict(row),
                    return_q=return_q,
                    return_sort=return_sort,
                    return_page=return_page,
                    edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
                )
            if url_changed:
                conn.execute(
                    "UPDATE bookmarks SET title = ?, url = ?, series_key = NULL WHERE id = ? AND user_id = ?",
                    (title, new_url, bookmark_id, user_id),
                )
            else:
                conn.execute(
                    "UPDATE bookmarks SET title = ? WHERE id = ? AND user_id = ?",
                    (title, bookmark_id, user_id),
                )
        if url_changed:
            try:
                check_single(bookmark_id, user_id)
                flash("Series updated — latest chapter data refreshed for the new URL.", "success")
            except Exception:
                log.exception("check_single after edit_bookmark URL change failed")
                flash(
                    "Series updated. Automatic check failed — use Check now on the dashboard to fetch chapter data.",
                    "warning",
                )
        else:
            flash("Series updated.", "success")
        return redirect_index_preserve_search()
    return render_template(
        "edit_bookmark.html",
        bookmark=dict(row),
        return_q=return_q,
        return_sort=return_sort,
        return_page=return_page,
        edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
    )


@app.route("/delete/<int:bookmark_id>", methods=["POST"])
def delete_bookmark(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect_index_preserve_search()


@csrf.exempt
@app.route("/api/series/ensure", methods=["POST"])
def ensure_series():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    url = (payload.get("url") or "").strip()
    series_key = (payload.get("series_key") or "").strip().lower()
    if not title or not url:
        return jsonify({"ok": False, "error": "title and url required"}), 400
    if not is_public_http_url(url):
        return jsonify({"ok": False, "error": "blocked URL"}), 400
    canonical_url = resolve_series_listing_url(url)
    cover_url = scrape_series_cover(canonical_url, title)
    with get_conn() as conn:
        existing = None
        if series_key:
            existing = conn.execute(
                "SELECT id, title, url, series_key FROM bookmarks WHERE user_id = ? AND series_key = ?",
                (user_id, series_key),
            ).fetchone()
        if existing is None:
            existing = conn.execute(
                "SELECT id, title, url, series_key FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, canonical_url),
            ).fetchone()

        if existing is not None:
            created = False
            row = existing
            if cover_url:
                conn.execute("UPDATE bookmarks SET cover_url = COALESCE(cover_url, ?) WHERE id = ?", (cover_url, row["id"]))
                row = conn.execute(
                    "SELECT id, title, url, series_key, cover_url FROM bookmarks WHERE id = ?",
                    (row["id"],),
                ).fetchone()
        else:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO bookmarks (user_id, title, url, series_key, cover_url) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, canonical_url, series_key or None, cover_url),
            )
            created = cursor.rowcount == 1
            row = conn.execute(
                "SELECT id, title, url, series_key, cover_url FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, canonical_url),
            ).fetchone()
            if row is None:
                return jsonify({"ok": False, "error": "series URL already exists under another local account"}), 409
    return jsonify({"ok": True, "created": created, "series": dict(row)})


@csrf.exempt
@app.route("/api/progress", methods=["POST"])
def save_progress():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    series_url = (payload.get("series_url") or "").strip()
    series_key = (payload.get("series_key") or "").strip().lower()
    chapter_url = (payload.get("chapter_url") or "").strip()
    chapter_label = (payload.get("chapter_label") or "").strip()
    chapter_num = payload.get("chapter_num")

    if not series_url and not series_key:
        return jsonify({"ok": False, "error": "series_url or series_key required"}), 400

    with get_conn() as conn:
        row = None
        if series_key:
            row = conn.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND series_key = ?",
                (user_id, series_key),
            ).fetchone()
        if row is None and series_url:
            row = conn.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, series_url),
            ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "series not found (ensure step failed or key mismatch)"}), 404
        bookmark_id = row["id"]

    parsed_num = None
    try:
        parsed_num = float(chapter_num) if chapter_num is not None else None
    except (TypeError, ValueError):
        parsed_num = None

    if not chapter_label:
        chapter_label = chapter_url or "Chapter"

    upsert_progress(user_id, bookmark_id, parsed_num, chapter_label, chapter_url)
    with get_conn() as conn:
        current = conn.execute(
            "SELECT latest_seen_num FROM bookmarks WHERE id = ?",
            (bookmark_id,),
        ).fetchone()
        current_num = current["latest_seen_num"] if current else None
        if parsed_num is not None and (current_num is None or parsed_num > current_num):
            # Keep latest_seen in sync from actual reading events if scraping lags/fails.
            conn.execute(
                """
                UPDATE bookmarks
                SET latest_seen = ?, latest_seen_num = ?, latest_seen_url = ?, last_checked = ?, last_error = NULL
                WHERE id = ?
                """,
                (
                    chapter_label,
                    parsed_num,
                    chapter_url or None,
                    datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    bookmark_id,
                ),
            )
    return jsonify({"ok": True, "bookmark_id": bookmark_id, "chapter_num": parsed_num})


@csrf.exempt
@app.route("/api/unread-count", methods=["GET"])
def api_unread_count():
    """Return the total unread chapter count for the actor user.

    Mirrors the dashboard aggregate (latest_seen_num minus the most recent
    reading_progress.chapter_num per bookmark, floored at zero) so the
    extension's badge can show the same number the user sees on the site.
    """
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT b.id AS bookmark_id,
                   b.title AS title,
                   b.series_key AS series_key,
                   b.latest_seen_num AS latest_num,
                   b.new_update AS new_update,
                   rp.chapter_num AS read_num
            FROM bookmarks b
            LEFT JOIN (
                SELECT x.bookmark_id, x.chapter_num
                FROM reading_progress x
                INNER JOIN (
                    SELECT bookmark_id, MAX(id) AS max_id
                    FROM reading_progress
                    WHERE user_id = ?
                    GROUP BY bookmark_id
                ) y ON y.bookmark_id = x.bookmark_id AND y.max_id = x.id
                WHERE x.user_id = ?
            ) rp ON rp.bookmark_id = b.id
            WHERE b.user_id = ?
            """,
            (user_id, user_id, user_id),
        ).fetchall()

    total_unread = 0.0
    behind_count = 0
    series = []
    tracked_keys = []
    for row in rows:
        latest_num = row["latest_num"]
        read_num = row["read_num"]
        sk = row["series_key"]
        if sk:
            tracked_keys.append(sk)
        unread = 0.0
        if latest_num is not None and read_num is not None:
            try:
                unread = max(0.0, float(latest_num) - float(read_num))
            except (TypeError, ValueError):
                unread = 0.0
        elif latest_num is not None and read_num is None and row["new_update"]:
            try:
                unread = max(0.0, float(latest_num))
            except (TypeError, ValueError):
                unread = 0.0
        if unread > 0:
            total_unread += unread
            behind_count += 1
            series.append(
                {
                    "bookmark_id": row["bookmark_id"],
                    "title": row["title"],
                    "series_key": sk,
                    "unread": int(unread) if float(unread).is_integer() else round(unread, 1),
                }
            )

    return jsonify(
        {
            "ok": True,
            "unread": int(total_unread) if float(total_unread).is_integer() else round(total_unread, 1),
            "behind": behind_count,
            "series": series,
            "tracked_keys": tracked_keys,
        }
    )


@csrf.exempt
@app.route("/api/debug/scrape", methods=["POST"])
def debug_scrape():
    if not admin_api_authorized():
        # Return 404 in production so the route is not discoverable as an open proxy.
        return jsonify({"ok": False, "error": "not found"}), 404
    payload = request.get_json(silent=True) or {}
    raw_url = (payload.get("url") or "").strip()
    if not raw_url:
        return jsonify({"ok": False, "error": "url required"}), 400

    resolved_url = resolve_series_listing_url(raw_url)
    try:
        res = SESSION.get(resolved_url, timeout=25)
        res.raise_for_status()
    except Exception as exc:
        return jsonify(
            {
                "ok": False,
                "url": raw_url,
                "resolved_url": resolved_url,
                "error": f"fetch_failed: {exc}",
                "error_flags": ["fetch_failed"],
            }
        ), 502

    soup = BeautifulSoup(res.text, "html.parser")
    details = pick_best_candidate_with_debug(soup, resolved_url)
    series_slug = extract_series_slug(resolved_url)

    return jsonify(
        {
            "ok": True,
            "url": raw_url,
            "resolved_url": resolved_url,
            "series_slug": series_slug,
            "picked_latest": {
                "label": details["label"],
                "chapter_num": details["chapter_num"],
                "url": details["chapter_url"],
            },
            "confidence": details["confidence"],
            "parser_version": details["parser_version"],
            "candidate_links": details["candidates"][:80],
            "candidate_count": len(details["candidates"]),
            "error_flags": details["error_flags"],
        }
    )


@csrf.exempt
@app.route("/api/maintenance/merge-duplicates", methods=["POST"])
def merge_duplicates():
    if not admin_api_authorized():
        return jsonify({"ok": False, "error": "not found"}), 404
    user_id = get_actor_user_id()
    merged_groups = 0
    deleted_bookmarks = 0

    with get_conn() as conn:
        group_query = """
            SELECT series_key, {agg} AS ids
            FROM bookmarks
            WHERE user_id = ? AND series_key IS NOT NULL AND TRIM(series_key) <> ''
            GROUP BY series_key
            HAVING COUNT(*) > 1
        """.format(
            agg="STRING_AGG(CAST(id AS TEXT), ',')" if IS_POSTGRES else "GROUP_CONCAT(id)"
        )
        groups = conn.execute(group_query, (user_id,)).fetchall()

        for group in groups:
            ids = [int(x) for x in (group["ids"] or "").split(",") if x]
            if len(ids) < 2:
                continue
            ids.sort()
            keeper_id = ids[0]
            duplicate_ids = ids[1:]
            merged_groups += 1

            keeper = conn.execute(
                "SELECT latest_seen_num, latest_seen, new_update, title FROM bookmarks WHERE id = ?",
                (keeper_id,),
            ).fetchone()
            best_num = keeper["latest_seen_num"] if keeper else None
            best_label = keeper["latest_seen"] if keeper else None
            best_new_update = int(keeper["new_update"]) if keeper else 0
            best_title = keeper["title"] if keeper else ""

            for dup_id in duplicate_ids:
                dup = conn.execute(
                    "SELECT latest_seen_num, latest_seen, new_update, title FROM bookmarks WHERE id = ?",
                    (dup_id,),
                ).fetchone()
                if dup:
                    dup_num = dup["latest_seen_num"]
                    if dup_num is not None and (best_num is None or dup_num > best_num):
                        best_num = dup_num
                        best_label = dup["latest_seen"]
                    best_new_update = max(best_new_update, int(dup["new_update"] or 0))
                    if len((dup["title"] or "").strip()) > len((best_title or "").strip()):
                        best_title = dup["title"]

                conn.execute(
                    """
                    INSERT OR IGNORE INTO reading_progress (user_id, bookmark_id, chapter_num, chapter_label, source_url, seen_at)
                    SELECT user_id, ?, chapter_num, chapter_label, source_url, seen_at
                    FROM reading_progress
                    WHERE bookmark_id = ?
                    """,
                    (keeper_id, dup_id),
                )
                conn.execute("DELETE FROM reading_progress WHERE bookmark_id = ?", (dup_id,))
                conn.execute("DELETE FROM bookmarks WHERE id = ?", (dup_id,))
                deleted_bookmarks += 1

            conn.execute(
                """
                UPDATE bookmarks
                SET latest_seen_num = ?, latest_seen = ?, new_update = ?, title = ?
                WHERE id = ?
                """,
                (best_num, best_label, best_new_update, best_title, keeper_id),
            )

    return jsonify(
        {
            "ok": True,
            "merged_groups": merged_groups,
            "deleted_bookmarks": deleted_bookmarks,
        }
    )


def setup_scheduler() -> Optional[BackgroundScheduler]:
    global _SCHEDULER
    with _SCHEDULER_LOCK:
        if _SCHEDULER is not None:
            return _SCHEDULER
        if os.getenv("DISABLE_AUTO_CHECK") == "1":
            return None
        interval = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            check_all_users,
            "interval",
            minutes=max(interval, 1),
            id="auto-check",
            max_instances=1,
            coalesce=True,
        )
        if READ_PROGRESS_MAX_PER_USER > 0:
            prune_interval = max(int(os.getenv("PROGRESS_PRUNE_INTERVAL_HOURS", "6")), 1)
            scheduler.add_job(
                prune_reading_progress_all_users,
                "interval",
                hours=prune_interval,
                id="progress-prune",
                max_instances=1,
                coalesce=True,
            )
        scheduler.start()
        _SCHEDULER = scheduler
    if INITIAL_AUTO_CHECK:
        try:
            check_all_users()
        except Exception:
            log.exception("initial check_all_users failed")
    return _SCHEDULER


def _should_autostart_scheduler() -> bool:
    if os.getenv("SCHEDULER_ENABLED", "1") != "1":
        return False
    # For multi-worker/process deployments, run scheduler in exactly one
    # designated instance by setting SCHEDULER_LEADER=1 on that instance only.
    if os.getenv("SCHEDULER_LEADER", "1") != "1":
        return False
    if os.getenv("DISABLE_AUTO_CHECK") == "1":
        return False
    if APP_DEBUG and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


if _should_autostart_scheduler():
    try:
        ensure_db_ready()
        setup_scheduler()
    except Exception:
        log.exception("scheduler autostart failed")


if __name__ == "__main__":
    ensure_db_ready()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=APP_DEBUG)

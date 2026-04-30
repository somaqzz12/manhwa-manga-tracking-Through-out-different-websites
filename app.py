import math
import os
import re
import smtplib
from dataclasses import asdict
from collections import defaultdict
import sqlite3
import json
import ipaddress
import logging
import secrets
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urljoin, urlparse
from xml.sax.saxutils import escape as xml_escape

from email.message import EmailMessage

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, Response, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from routes.api_discovery import register_api_discovery_routes
from routes.library import register_library_routes
from routes.public import register_public_routes
from werkzeug.security import check_password_hash, generate_password_hash
from services import chapter_parsing as chapter
from services import discovery
from services import reading_insights
from services import source_registry
from services import story_groups
from sources import registry as policy_registry
from sources.resolver import normalize_url as source_engine_normalize_url
from sources.resolver import resolve_url as source_engine_resolve_url
from sources.resolver import search_title as source_engine_search_title
from sources.registry import supported_source_policy
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


def _now_iso_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


@app.template_filter("clean")
def clean_number(value):
    """Render chapter-like numeric values without noisy trailing .0."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    text = str(value).strip()
    if not text:
        return ""
    try:
        num = float(text)
    except ValueError:
        return text
    return str(int(num)) if num.is_integer() else f"{num:g}"


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
    return (
        render_template(
            "auth.html",
            mode=(request.args.get("mode") or "login"),
            error="Too many attempts. Please wait a minute and try again.",
            auth_next=_safe_internal_redirect_path((request.args.get("next") or "").strip()) or "",
        ),
        429,
    )

HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
MAX_CHECK_WORKERS = max(1, int(os.getenv("MAX_CHECK_WORKERS", "6")))
SCRAPE_RETRY_ON_FAIL = os.getenv("SCRAPE_RETRY_ON_FAIL", "0") == "1"
SCRAPE_TIMING_LOGS = os.getenv("SCRAPE_TIMING_LOGS", "0") == "1"
USE_SELENIUM_FALLBACK = os.getenv("USE_SELENIUM_FALLBACK", "0") == "1"
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "local@tracker")
MIN_PASSWORD_LENGTH = max(1, int(os.getenv("MIN_PASSWORD_LENGTH", "8")))
READ_PROGRESS_MAX_PER_BOOKMARK = int(os.getenv("READ_PROGRESS_MAX_PER_BOOKMARK", "400"))
INITIAL_AUTO_CHECK = os.getenv("INITIAL_AUTO_CHECK", "0") == "1"
CHECK_STALE_MINUTES = max(1, int(os.getenv("CHECK_STALE_MINUTES", "45")))
DEFAULT_BUG_REPORT_URL = "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites/issues"
APP_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"

_DEMO_STORY_MERGED = "sg-demomerged"


DEMO_BOOKMARKS = [
    {
        "id": 101,
        "title": "Demo: Same story, two sources (best chapter wins)",
        "url": "https://asurascans.com/manga/demo-fake",
        "story_id": _DEMO_STORY_MERGED,
        "cover_url": None,
        "new_update": 1,
        "read_chapter_num": 170.0,
        "read_chapter_label": "Ch 170",
        "read_source_url": "https://asurascans.com/manga/demo-fake/ch/170",
        "latest_seen_num": 174.0,
        "latest_seen_url": "https://asurascans.com/manga/demo-fake/ch/174",
        "latest_seen": "Ch 174",
        "last_checked": "2026-04-01T00:00:00Z",
        "last_error": None,
        "latest_parser_version": "asurascans-selector",
        "latest_error_flags": "",
        "genre": "",
        "series_key": None,
    },
    {
        "id": 102,
        "title": "Demo: Same story (alternate site farther ahead)",
        "url": "https://mangadex.org/title/00000000-0000-0000-0000-000000000001",
        "story_id": _DEMO_STORY_MERGED,
        "cover_url": None,
        "new_update": 1,
        "read_chapter_num": 170.0,
        "read_chapter_label": "Ch 170",
        "read_source_url": "https://mangadex.org/chapter/demo",
        "latest_seen_num": 176.0,
        "latest_seen_url": "https://mangadex.org/chapter/demo176",
        "latest_seen": "Ch 176",
        "last_checked": "2026-04-01T00:00:00Z",
        "last_error": None,
        "latest_parser_version": "mangadex-api",
        "latest_error_flags": "",
        "genre": "",
        "series_key": None,
    },
    {
        "id": 103,
        "title": "Demo: Solo leveling-style binge backlog",
        "url": "https://example.com/manga/solo-demo",
        "story_id": "sg-demosolo",
        "cover_url": None,
        "new_update": 1,
        "read_chapter_num": 10.0,
        "read_chapter_label": "Ch 10",
        "read_source_url": "",
        "latest_seen_num": 18.0,
        "latest_seen_url": "https://example.com/manga/solo-demo/ch-18",
        "latest_seen": "Ch 18",
        "last_checked": "2026-04-01T00:00:00Z",
        "last_error": None,
        "latest_parser_version": "generic-heuristic",
        "latest_error_flags": "",
        "genre": "",
        "series_key": None,
    },
]
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
ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME") or "").strip().lower()
READ_PROGRESS_MAX_PER_USER = int(os.getenv("READ_PROGRESS_MAX_PER_USER", "20000"))
BOOKMARKS_PAGE_SIZE = max(1, int(os.getenv("BOOKMARKS_PAGE_SIZE", "60")))
UI_SHOW_SOURCE_HOSTS = os.getenv("UI_SHOW_SOURCE_HOSTS", "0") == "1"
SORT_MODES = frozenset({"added", "title", "updated", "unread"})
IMPORT_MAX_BYTES = int(os.getenv("IMPORT_MAX_BYTES", str(5 * 1024 * 1024)))
IMPORT_MAX_ITEMS = int(os.getenv("IMPORT_MAX_ITEMS", "20000"))
AUTH_RATE_LIMIT_PER_IP = os.getenv("AUTH_RATE_LIMIT_PER_IP", "10/minute;60/hour")
AUTH_RATE_LIMIT_PER_USER = os.getenv("AUTH_RATE_LIMIT_PER_USER", "8/minute;30/hour")
DEAD_SERIES_WARNING_DAYS = max(1, int(os.getenv("DEAD_SERIES_WARNING_DAYS", "120")))
RESOLVE_URL_MAX_LEN = int(os.getenv("RESOLVE_URL_MAX_LEN", "2048"))
DISCOVER_QUERY_MAX_LEN = int(os.getenv("DISCOVER_QUERY_MAX_LEN", "120"))
RESOLVE_CACHE_TTL_SECONDS = int(os.getenv("RESOLVE_CACHE_TTL_SECONDS", "120"))
_PUBLIC_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,40}[a-z0-9])?$")
if not APP_DEBUG and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set in production")

_RESOLVE_CACHE_LOCK = threading.Lock()
_RESOLVE_CACHE: dict[str, tuple[float, dict]] = {}
_DISCOVER_LIVE_CACHE: dict[str, tuple[float, dict]] = {}


_DEFAULT_GITHUB_URL = "https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites"


def _extension_zip_download_url() -> str:
    """Public one-click ZIP of the `extension/` tree (for Load unpacked)."""
    custom = (os.getenv("EXTENSION_ZIP_DOWNLOAD_URL") or "").strip()
    if custom:
        return custom
    gh = (os.getenv("GITHUB_URL") or _DEFAULT_GITHUB_URL).strip().rstrip("/")
    tree = f"{gh}/tree/main/extension"
    return "https://download-directory.github.io/?url=" + quote(tree, safe="")


@app.context_processor
def inject_template_globals():
    return {
        "bug_report_href": os.getenv("BUG_REPORT_URL", DEFAULT_BUG_REPORT_URL),
        "contact_email": os.getenv("CONTACT_EMAIL", "").strip(),
        "site_description": "Discover manga and manhwa. Search titles or paste URLs, compare sources, and track updates everywhere.",
        "min_password_length": MIN_PASSWORD_LENGTH,
        "github_url": (os.getenv("GITHUB_URL") or _DEFAULT_GITHUB_URL).strip(),
        "extension_zip_download_url": _extension_zip_download_url(),
    }


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def get_profile_for_url(url: str) -> Optional[dict]:
    return source_registry.get_profile_for_url(url)


@app.template_global("build_source_bug_report_url")
def build_source_bug_report_url(
    *,
    source_id: str,
    domain: str = "",
    series_url: str = "",
    last_error: str = "",
    parser_version: str = "",
) -> str:
    report = (os.getenv("BUG_REPORT_URL") or DEFAULT_BUG_REPORT_URL or "").strip()
    if not report:
        return "#"
    title = f"[Source] {source_id} broken or misparsed"
    body = (
        f"**Source id:** {source_id}\n\n"
        f"**Domain:** {domain}\n\n"
        f"**Series URL:** {series_url}\n\n"
        f"**Last error:** {last_error or '_(none)_'}\n\n"
        f"**Parser version:** {parser_version or '_(none)_'}\n"
    )
    if "github.com" in report.lower():
        report = report.rstrip("/")
        lower = report.lower()
        if lower.endswith("/issues"):
            report = report[: -len("/issues")]
            lower = report.lower()
        if not lower.endswith("/issues/new"):
            report = report + "/issues/new"
    sep = "&" if "?" in report else "?"
    return report + sep + "title=" + quote(title) + "&body=" + quote(body)


@app.template_global()
def source_bug_report_href(bookmark) -> str:
    if not bookmark:
        return "#"
    url = (bookmark.get("url") or "").strip()
    prof = get_profile_for_url(url) or {}
    sid = str(prof.get("id") or urlparse(url).netloc or "unknown")
    return build_source_bug_report_url(
        source_id=sid,
        domain=urlparse(url).netloc,
        series_url=url,
        last_error=str(bookmark.get("last_error") or ""),
        parser_version=str(bookmark.get("latest_parser_version") or ""),
    )


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
    now = _now_iso_z()
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


_SKIP_DB_READY_ENDPOINTS = frozenset(
    {"healthz", "sources_page", "privacy_page", "changelog_page", "demo_dashboard"}
)


@app.before_request
def handle_preflight():
    # /healthz must stay free of DB and heavy work so uptime pings and free-tier
    # keep-alive cron jobs do not trigger init_db or migrations.
    if request.endpoint not in _SKIP_DB_READY_ENDPOINTS:
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
        return
    cols = conn.execute("PRAGMA table_info(bookmarks)").fetchall()
    names = {c["name"] for c in cols}
    if "canonical_title" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN canonical_title TEXT")
    if "description" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN description TEXT")
    if "chapter_count" not in names:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN chapter_count INTEGER")


def _ensure_users_integration_columns(conn) -> None:
    """RSS secret, optional webhooks, API token, optional public list slug."""
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

        # Ensure a default local user exists so extension flow keeps working.
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


def fetch_public_url(url: str, **kwargs) -> requests.Response:
    """Fetch a public URL while revalidating every redirect target."""
    current = (url or "").strip()
    max_redirects = int(kwargs.pop("max_redirects", 5))
    timeout = kwargs.pop("timeout", HTTP_TIMEOUT_SECONDS)
    for _ in range(max_redirects + 1):
        if not is_public_http_url(current):
            raise ValueError("Blocked URL (private/internal host)")
        res = SESSION.get(current, timeout=timeout, allow_redirects=False, **kwargs)
        if not res.is_redirect:
            return res
        location = (res.headers.get("Location") or "").strip()
        if not location:
            return res
        current = urljoin(current, location)
    raise ValueError("Too many redirects")


def normalize_bookmark_url(raw_url: str) -> str:
    """Normalize URL for duplicate checks (trim, strip trailing slash, case-fold)."""
    return (raw_url or "").strip().rstrip("/").lower()


def parse_backup_int(value) -> Optional[int]:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return None


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


def _normalize_title_duplicate_key(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split()).strip()


def _load_duplicate_hints(user_id: int, limit: int = 40) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, story_id, url, series_key FROM bookmarks WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
    by_key: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = _normalize_title_duplicate_key(str(r["title"] or ""))
        if len(key) < 4:
            continue
        by_key[key].append(
            {
                "id": int(r["id"]),
                "title": r["title"],
                "story_id": r["story_id"],
                "url": r["url"],
                "series_key": r["series_key"],
            }
        )
    hints: list[dict] = []
    for key, items in by_key.items():
        if len(items) < 2:
            continue
        sids = {story_groups.effective_story_id(x) for x in items}
        if len(sids) < 2:
            continue
        ids_sorted = sorted(int(x["id"]) for x in items)
        keeper_id = ids_sorted[0]
        merge_ids = ids_sorted[1:]
        hints.append(
            {
                "normalized_title": key,
                "items": items,
                "keeper_id": keeper_id,
                "merge_ids": merge_ids,
            }
        )
    hints.sort(key=lambda h: (-len(h["items"]), h["normalized_title"]))
    return hints[:limit]


def _days_since_iso_optional(ts: Optional[str]) -> Optional[float]:
    if not ts:
        return None
    try:
        tsi = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(tsi)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _fetch_user_story_rows(user_id: int, search_q: str = "") -> tuple[list[dict], dict[int, dict]]:
    title_clause, title_params = _bookmark_title_search_clause(search_q)
    with get_conn() as conn:
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
            """,
            (user_id, user_id, user_id, *title_params),
        ).fetchall()
    raw_rows = [dict(r) for r in rows]
    raw_by_id = {int(r["id"]): r for r in raw_rows}
    return raw_rows, raw_by_id


def _build_sorted_story_cards(raw_rows: list[dict], raw_by_id: dict[int, dict], sort: str) -> list[dict]:
    story_cards = story_groups.group_and_aggregate(raw_rows)
    story_groups.attach_sort_keys(story_cards, raw_by_id)
    return story_groups.sort_story_cards(story_cards, sort)


def _notify_discord_new_chapter(series_title: str, chapter_label: Optional[str], chapter_url: Optional[str]) -> None:
    webhook = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    if not webhook:
        return
    line = f"**New chapter:** {series_title}\n{(chapter_label or '').strip() or '—'}"
    if chapter_url:
        line += f"\n{chapter_url}"
    try:
        requests.post(webhook, json={"content": line[:1900]}, timeout=6)
    except Exception:
        log.exception("discord webhook post failed")


def _notify_user_webhook(user_id: int, series_title: str, chapter_label: Optional[str], chapter_url: Optional[str]) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT webhook_url FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not (row["webhook_url"] or "").strip():
        return
    wh = row["webhook_url"].strip()
    if not is_public_http_url(wh):
        return
    payload = {
        "event": "chapter_update",
        "title": series_title,
        "chapter": chapter_label,
        "url": chapter_url,
    }
    try:
        requests.post(wh, json=payload, timeout=8)
    except Exception:
        log.exception("user webhook post failed")


def _notify_user_email_new_chapter(
    user_id: int, series_title: str, chapter_label: Optional[str], chapter_url: Optional[str]
) -> None:
    """SMTP optional (`SMTP_HOST`): notifies opted-in users when a scrape finds a newer chapter."""
    smtp_host = (os.getenv("SMTP_HOST") or "").strip()
    if not smtp_host:
        return
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    user_s = (os.getenv("SMTP_USER") or "").strip()
    password = os.getenv("SMTP_PASSWORD") or ""
    mail_from = (os.getenv("SMTP_FROM") or user_s or "").strip()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT email, notify_email_chapters FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return
    try:
        if int(row["notify_email_chapters"] or 0) != 1:
            return
    except (TypeError, ValueError):
        return

    to_addr = (row["email"] or "").strip()
    if (
        not to_addr
        or to_addr.strip().lower() == DEFAULT_USER_EMAIL.strip().lower()
    ):
        return
    if not mail_from:
        return

    lines = [
        "Hello — your manga watchlist found a new chapter:",
        "",
        f"Series: {series_title}",
        f"Chapter: {(chapter_label or '').strip() or '—'}",
        f"Link: {(chapter_url or '').strip() or '—'}",
    ]
    msg = EmailMessage()
    msg["Subject"] = f"New chapter: {series_title}"
    msg["From"] = mail_from
    msg["To"] = to_addr
    msg.set_content("\n".join(lines))

    try:
        if port == 465:
            context = __import__("ssl").create_default_context()
            with smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=12) as smtp:
                if user_s:
                    smtp.login(user_s, password)
                smtp.send_message(msg)
            return
        with smtplib.SMTP(smtp_host, port, timeout=12) as smtp:
            smtp.ehlo()
            smtp.starttls(context=__import__("ssl").create_default_context())
            smtp.ehlo()
            if user_s:
                smtp.login(user_s, password)
            smtp.send_message(msg)
    except Exception:
        log.exception("SMTP notify failed")


def _ensure_user_rss_token(conn, user_id: int) -> str:
    row = conn.execute("SELECT rss_feed_token FROM users WHERE id = ?", (user_id,)).fetchone()
    if row and (row["rss_feed_token"] or "").strip():
        return str(row["rss_feed_token"]).strip()
    tok = secrets.token_urlsafe(16)
    conn.execute("UPDATE users SET rss_feed_token = ? WHERE id = ?", (tok, user_id))
    return tok


def _user_id_from_bearer_api_token(raw: str) -> Optional[int]:
    t = (raw or "").strip()
    if not t:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE api_access_token = ?", (t,)).fetchone()
    return int(row["id"]) if row else None


def _rss_item_date(iso_ts: Optional[str]) -> str:
    if not iso_ts:
        dt = datetime.now(timezone.utc)
    else:
        try:
            dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        except Exception:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _render_user_rss_xml(user_id: int, base_url: str) -> str:
    raw_rows, raw_by_id = _fetch_user_story_rows(user_id, "")
    cards = _build_sorted_story_cards(raw_rows, raw_by_id, "updated")[:100]
    base = (base_url or "").rstrip("/") or ""
    chan_title = xml_escape("Manga Watchlist")
    chan_link = xml_escape(base)
    chan_desc = xml_escape("Tracked series — latest chapters from your library")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        f"<title>{chan_title}</title>",
        f"<link>{chan_link}</link>",
        f"<description>{chan_desc}</description>",
        f"<lastBuildDate>{_rss_item_date(None)}</lastBuildDate>",
    ]
    for c in cards:
        title = xml_escape(str(c.get("title") or "Untitled"))
        href = (c.get("continue_url") or c.get("url") or base).strip()
        link = xml_escape(href if href else base)
        lbl = str(c.get("latest_seen") or "").strip()
        desc_bits = []
        if lbl:
            desc_bits.append(f"Latest: {lbl}")
        rc = c.get("read_chapter_num")
        if rc is not None:
            try:
                rn = float(rc)
                rn_s = str(int(rn)) if rn.is_integer() else f"{rn:g}"
                desc_bits.append(f"Last read: Ch. {rn_s}")
            except (TypeError, ValueError):
                pass
        desc = xml_escape(" · ".join(desc_bits) if desc_bits else "Tracked series")
        ts = c.get("_last_checked") or ""
        bid = int(c.get("id") or 0)
        guid = xml_escape(f"{user_id}-{bid}-{ts}")
        parts.append("<item>")
        parts.append(f"<title>{title}</title>")
        parts.append(f"<link>{link}</link>")
        parts.append(f"<description>{desc}</description>")
        parts.append(f"<pubDate>{_rss_item_date(str(ts) if ts else '')}</pubDate>")
        parts.append(f'<guid isPermaLink="false">{guid}</guid>')
        parts.append("</item>")
    parts.extend(["</channel>", "</rss>"])
    return "\n".join(parts)


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


def _safe_internal_redirect_path(candidate: str | None) -> str | None:
    """Return path+query if safe for post-auth redirects (same-origin relative only)."""
    if not candidate:
        return None
    s = candidate.strip()
    if not s.startswith("/") or s.startswith("//") or "\n" in s or "\r" in s or "\\" in s:
        return None
    return s


def _login_redirect_preserve_destination() -> Response:
    return redirect(url_for("auth_page", mode="login", next=request.full_path))


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


def _admin_secret_from_request() -> str:
    """Read admin API token from headers only (never query strings — referrers/history leak)."""
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Admin-Token") or "").strip()


def admin_api_authorized() -> bool:
    """Destructive / scrape-proxy JSON routes: debug token, or admin username session, or FLASK_DEBUG."""
    if APP_DEBUG:
        return True
    if ADMIN_API_TOKEN:
        provided = _admin_secret_from_request()
        if provided and provided == ADMIN_API_TOKEN:
            return True
    if ADMIN_USERNAME:
        current = get_current_user()
        if current:
            try:
                if str(current.get("username") or "").strip().lower() == ADMIN_USERNAME.strip().lower():
                    return True
            except Exception:
                pass
    return False


def admin_view_authorized() -> bool:
    """Allow admin HTML pages for configured admin user or the same header token as the API.

    Browser navigation cannot safely carry secrets in query strings; use a normal
    login as ``ADMIN_USERNAME`` or a reverse-proxy that injects ``X-Admin-Token``.
    """
    if APP_DEBUG:
        return True
    current = get_current_user()
    if current and ADMIN_USERNAME:
        try:
            current_username = str(current["username"] or "").strip().lower()
        except Exception:
            current_username = ""
        if current_username == ADMIN_USERNAME:
            return True
    if ADMIN_API_TOKEN:
        provided = _admin_secret_from_request()
        if provided and provided == ADMIN_API_TOKEN:
            return True
    return False


def _admin_link_kw() -> dict:
    """Reserved for backward-compatible templates; admin secrets are never embedded in URLs."""
    return {}


def _public_slug_ok(candidate: Optional[str]) -> bool:
    s = (candidate or "").strip().lower()
    if len(s) < 3 or len(s) > 42:
        return False
    return bool(_PUBLIC_SLUG_RE.fullmatch(s))


def _api_v1_rate_limit_key() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if tok:
            return f"api-v1:{tok}"
    return get_remote_address()


def _cache_get(cache: dict[str, tuple[float, dict]], key: str, ttl_seconds: int) -> Optional[dict]:
    now = time.time()
    with _RESOLVE_CACHE_LOCK:
        item = cache.get(key)
        if not item:
            return None
        ts, payload = item
        if now - ts > ttl_seconds:
            cache.pop(key, None)
            return None
        return dict(payload)


def _cache_set(cache: dict[str, tuple[float, dict]], key: str, payload: dict) -> None:
    with _RESOLVE_CACHE_LOCK:
        cache[key] = (time.time(), dict(payload))


def _image_url_from_node(node, base_url: str) -> Optional[str]:
    if node is None:
        return None
    src = ""
    if getattr(node, "name", None) == "img":
        src = (
            (node.get("src") or node.get("data-src") or node.get("data-lazy-src") or node.get("data-original") or "")
            .strip()
        )
    elif hasattr(node, "get"):
        src = (node.get("src") or "").strip()
        if not src:
            style = (node.get("style") or "") or ""
            m = re.search(r"url\(\s*['\"]?([^'\"()]+)['\"]?\s*\)", style, re.I)
            if m:
                src = m.group(1).strip()
        if not src and node.get("content"):
            src = (node.get("content") or "").strip()
    if not src and hasattr(node, "select_one"):
        inner = node.select_one("img")
        if inner is not None:
            return _image_url_from_node(inner, base_url)
    if not src:
        return None
    candidate = urljoin(base_url, src)
    return candidate if is_public_http_url(candidate) else None


def scrape_series_cover(url: str, series_title: str = "") -> Optional[str]:
    if not is_public_http_url(url):
        return None
    try:
        res = fetch_public_url(url)
        res.raise_for_status()
    except Exception:
        return None

    fetched_url = str(res.url or url).strip()
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
            candidate = urljoin(fetched_url or url, value.strip())
            return candidate if is_public_http_url(candidate) else None

    profile = get_profile_for_url(url)
    merged_title = (series_title or "").strip()
    if profile:
        ts = (profile.get("title_selector") or "").strip()
        if ts:
            tnode = soup.select_one(ts)
            if tnode:
                ttext = tnode.get_text(" ", strip=True)
                if ttext:
                    merged_title = merged_title or ttext
        cs = (profile.get("cover_selector") or "").strip()
        if cs:
            cnode = soup.select_one(cs)
            cover_guess = _image_url_from_node(cnode, fetched_url or url)
            if cover_guess:
                return cover_guess

    title_tokens = {t for t in re.split(r"[^a-z0-9]+", (merged_title or "").lower()) if len(t) >= 3}
    best_src: Optional[str] = None
    best_score = -10
    for img in soup.select("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        full_src = urljoin(fetched_url or url, src)
        if not is_public_http_url(full_src):
            continue
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
        res = fetch_public_url(url)
        res.raise_for_status()
    except Exception:
        return url

    final_url = str(res.url or url).strip()
    soup = BeautifulSoup(res.text, "html.parser")
    candidates: list[str] = []
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        candidates.append(urljoin(final_url or url, canonical.get("href", "").strip()))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get("content"):
        candidates.append(urljoin(final_url or url, og_url.get("content", "").strip()))
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

    candidates = [c for c in candidates if c and is_public_http_url(c)]
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
            if not is_public_http_url(absolute):
                continue
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


def scrape_with_profile(soup: BeautifulSoup, page_url: str, profile: dict) -> dict:
    selector = (profile.get("chapter_link_selector") or profile.get("chapter_selector") or "").strip()
    sid = (profile.get("id") or "site").strip()
    pv_base = f"{sid}-selector"
    if not selector:
        return {
            "label": None,
            "chapter_num": None,
            "chapter_url": None,
            "confidence": 0.0,
            "parser_version": f"{pv_base}-missing",
            "error_flags": ["missing_selector"],
        }

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
        return {
            "label": None,
            "chapter_num": None,
            "chapter_url": None,
            "confidence": 0.0,
            "parser_version": pv_base,
            "error_flags": ["profile_no_match"],
        }
    return {
        "label": best["label"],
        "chapter_num": best["chapter_num"],
        "chapter_url": best["chapter_url"],
        "confidence": 0.95,
        "parser_version": pv_base,
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
        # Fallback: title may lack English feeds; retry without translatedLanguage filter.
        api_any = (
            "https://api.mangadex.org/chapter"
            f"?manga={manga_id}"
            "&limit=1"
            "&order[chapter]=desc"
            "&contentRating[]=safe"
            "&contentRating[]=suggestive"
            "&contentRating[]=erotica"
            "&contentRating[]=pornographic"
        )
        try:
            res2 = SESSION.get(api_any, timeout=HTTP_TIMEOUT_SECONDS)
            res2.raise_for_status()
            payload2 = res2.json()
            data = payload2.get("data") or []
        except Exception:
            pass
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
    if profile and profile.get("api"):
        return scrape_mangadex_api(url)
    t_fetch = time.perf_counter()
    try:
        res = fetch_public_url(url)
        res.raise_for_status()
    except Exception as exc:
        _log_scrape_timing("html_fetch_failed", url, t_fetch)
        return None, None, None, f"Request failed: {exc}", {}
    _log_scrape_timing("html_fetch", url, t_fetch)

    fetched_url = str(res.url or url).strip() or url
    t_parse = time.perf_counter()
    soup = BeautifulSoup(res.text, "html.parser")
    _log_scrape_timing("html_parse", url, t_parse)
    t_extract = time.perf_counter()
    if profile and not profile.get("api"):
        info = scrape_with_profile(soup, fetched_url, profile)
        flags = set(info.get("error_flags") or [])
        if info.get("chapter_num") is None and flags.intersection({"profile_no_match", "missing_selector"}):
            # Site layout may have changed; generic parser often still works.
            fallback = pick_best_candidate_with_debug(soup, fetched_url)
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
        info = pick_best_candidate_with_debug(soup, fetched_url)
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

    if USE_SELENIUM_FALLBACK:
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
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_seconds = (now - ts).total_seconds()
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
        now = _now_iso_z()

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
        if new_update == 1:
            _notify_discord_new_chapter(str(row["title"] or ""), str(label) if label else None, latest_url)
            _notify_user_webhook(user_id, str(row["title"] or ""), str(label) if label else None, latest_url)
            _notify_user_email_new_chapter(user_id, str(row["title"] or ""), str(label) if label else None, latest_url)


def upsert_progress(user_id: int, bookmark_id: int, chapter_num: Optional[float], chapter_label: str, source_url: str) -> None:
    if chapter_num is None:
        chapter_num = parse_chapter_number(chapter_label) or parse_chapter_from_url(source_url)
    now = _now_iso_z()
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
        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            tst = ts.replace(tzinfo=timezone.utc)
        else:
            tst = ts.astimezone(timezone.utc)
        seconds = max(0, int((now - tst).total_seconds()))
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
    if login_required() and get_current_user() is not None:
        dest = _safe_internal_redirect_path((request.args.get("next") or "").strip())
        return redirect(dest or url_for("index"))

    mode = (request.args.get("mode") or "login").strip().lower()
    if mode not in ("login", "register"):
        mode = "login"
    error = None
    auth_next = _safe_internal_redirect_path((request.args.get("next") or "").strip()) or ""

    if request.method == "POST":
        posted_next = _safe_internal_redirect_path((request.form.get("next") or "").strip())
        if posted_next:
            auth_next = posted_next
        try:
            action = request.form.get("action", "login")
            username = (request.form.get("username") or "").strip().lower()
            password = request.form.get("password") or ""
            form_next = _safe_internal_redirect_path((request.form.get("next") or "").strip())
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
                        now = _now_iso_z()
                        synthetic_email = f"{username}@local.user"
                        insert_cur = conn.execute(
                            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                            (username, synthetic_email, generate_password_hash(password), now),
                        )
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
                        session.clear()
                        session["user_id"] = new_user_id
                        session["onboarding_pending"] = True
                        return redirect(form_next or url_for("index"))
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
                    return redirect(form_next or url_for("index"))
        except Exception:
            error = "Temporary database issue. Please try again in a few seconds."

    return render_template("auth.html", mode=mode, error=error, auth_next=auth_next)


@app.route("/login")
def login_alias():
    nxt = (request.args.get("next") or "").strip()
    return redirect(url_for("auth_page", mode="login", **({"next": nxt} if nxt else {})))


@app.route("/register")
def register_alias():
    nxt = (request.args.get("next") or "").strip()
    return redirect(url_for("auth_page", mode="register", **({"next": nxt} if nxt else {})))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("auth_page"))


_SOURCE_CATALOG_GROUP_ORDER = (
    "Automatic",
    "Supported",
    "Experimental",
    "Extension-assisted",
    "Manual",
    "Unavailable",
    "Other",
)


def _friendly_public_support_bucket(src: dict) -> str:
    """User-facing support label for public sources page (not raw policy enums)."""
    p = (src.get("policy_support_level") or "").strip().lower()
    if p == "official_api":
        return "Automatic"
    if p == "site_adapter":
        return "Supported"
    if p == "generic_detector":
        return "Experimental"
    if p == "manual_only":
        return "Manual"
    if p == "blocked":
        return "Unavailable"
    if p == "requested":
        return "Extension-assisted"
    if (src.get("registry_origin") or "").strip() == "manifest":
        return "Extension-assisted"
    if (src.get("registry_origin") or "").strip() == "curated":
        return "Supported"
    return "Other"


def _public_sources_catalog_view(raw_sources: list[dict]) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Drop imported manifest rows that have no policy match; keep curated and legacy rows."""
    filtered: list[dict] = []
    for src in raw_sources:
        origin = (src.get("registry_origin") or "").strip()
        pol = (src.get("policy_support_level") or "").strip()
        if origin == "manifest" and not pol:
            continue
        row = dict(src)
        row["friendly_support"] = _friendly_public_support_bucket(row)
        filtered.append(row)
    buckets: dict[str, list[dict]] = {k: [] for k in _SOURCE_CATALOG_GROUP_ORDER}
    for row in filtered:
        b = row["friendly_support"]
        if b not in buckets:
            b = "Other"
            row["friendly_support"] = "Other"
        buckets[b].append(row)
    groups = [(k, buckets[k]) for k in _SOURCE_CATALOG_GROUP_ORDER if buckets[k]]
    return filtered, groups


@app.route("/sources")
def sources_page():
    sources = source_registry.public_sources_with_health()
    policy_by_domain: dict[str, dict] = {}
    for row in policy_registry.SOURCE_REGISTRY:
        for dom in row.get("domains") or []:
            d = str(dom).strip().lower().lstrip(".")
            if d and d not in policy_by_domain:
                policy_by_domain[d] = row
    for src in sources:
        matched = None
        for dom in src.get("domains") or []:
            key = str(dom).strip().lower().lstrip(".")
            if key in policy_by_domain:
                matched = policy_by_domain[key]
                break
        src["policy_support_level"] = (matched or {}).get("support_level") or ""
        src["policy_risk_level"] = (matched or {}).get("risk_level") or ""
    catalog_sources, source_groups = _public_sources_catalog_view(sources)
    counts = source_registry.aggregate_status_counts(catalog_sources)
    health = source_registry.load_health()
    return render_template(
        "sources.html",
        sources=catalog_sources,
        source_groups=source_groups,
        counts=counts,
        health_updated_at=health.get("updated_at"),
        current_user=get_current_user(),
        demo_mode=False,
        search_q="",
        sort="added",
        page=1,
        check_all_status_text="",
        total_count=0,
    )


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/changelog")
def changelog_page():
    return render_template("changelog.html")


@app.route("/demo")
def demo_dashboard():
    demo_user = {"username": "demo", "email": "demo@local", "id": 0, "created_at": ""}
    raw_demo = [dict(b) for b in DEMO_BOOKMARKS]
    raw_by_id = {int(r["id"]): r for r in raw_demo}
    story_cards = _build_sorted_story_cards(raw_demo, raw_by_id, "added")
    tu = sum(float(c.get("unread_count") or 0) for c in story_cards)
    bc = sum(1 for c in story_cards if float(c.get("unread_count") or 0) > 0)
    tu_disp = int(tu) if float(tu).is_integer() else round(tu, 1)
    insights = reading_insights.build_insights(story_cards)
    all_caught_up_demo = len(story_cards) > 0 and bc == 0
    return render_template(
        "index.html",
        bookmarks=story_cards,
        current_user=demo_user,
        total_unread=tu_disp,
        behind_count=bc,
        page=1,
        total_pages=1,
        total_count=len(story_cards),
        page_size=BOOKMARKS_PAGE_SIZE,
        search_q="",
        sort="added",
        index_link_kw={},
        edit_link_kw={},
        check_all_running=False,
        check_all_status_text="Demo — data is fake",
        demo_mode=True,
        show_onboarding=False,
        all_caught_up=all_caught_up_demo,
        insights=insights,
        ui_show_source_hosts=UI_SHOW_SOURCE_HOSTS,
        duplicate_hints=[],
        rss_feed_url=None,
        stale_story_count=0,
        dead_series_days=DEAD_SERIES_WARNING_DAYS,
    )


@app.route("/onboarding/dismiss", methods=["POST"])
def onboarding_dismiss():
    if login_required():
        session.pop("onboarding_pending", None)
    return redirect(request.referrer or url_for("index"))


@app.route("/account/delete", methods=["GET", "POST"])
def delete_account():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        session.pop("user_id", None)
        return _login_redirect_preserve_destination()
    if str(current_user["email"] or "").strip().lower() == DEFAULT_USER_EMAIL.strip().lower():
        flash("The built-in local demo user cannot be deleted from this screen.", "error")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template(
            "delete_account.html",
            current_user=current_user,
            demo_mode=False,
            search_q="",
            sort="added",
            page=1,
        )
    password = request.form.get("password") or ""
    if not password:
        flash("Enter your password to confirm account deletion.", "error")
        return render_template(
            "delete_account.html",
            current_user=current_user,
            demo_mode=False,
            search_q="",
            sort="added",
            page=1,
        )
    with get_conn() as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            flash("Incorrect password.", "error")
            return render_template(
                "delete_account.html",
                current_user=current_user,
                demo_mode=False,
                search_q="",
                sort="added",
                page=1,
            )
        conn.execute("DELETE FROM reading_progress WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM bookmarks WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    session.clear()
    flash("Your account and all bookmarks have been deleted.", "info")
    return redirect(url_for("home"))


@app.route("/account/settings", methods=["GET", "POST"])
def account_settings():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        session.pop("user_id", None)
        return _login_redirect_preserve_destination()

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        if action == "issue_api_token":
            tok = secrets.token_urlsafe(24)
            with get_conn() as conn:
                conn.execute("UPDATE users SET api_access_token = ? WHERE id = ?", (tok, user_id))
            flash("New API token issued — copy it now; older tokens stop working.", "success")
            return redirect(url_for("account_settings"))

        wh = (request.form.get("webhook_url") or "").strip()
        if wh and not is_public_http_url(wh):
            flash("Webhook URL must be empty or a public http(s) URL.", "error")
            return redirect(url_for("account_settings"))
        slug_in = (request.form.get("public_list_slug") or "").strip().lower()
        if slug_in and not _public_slug_ok(slug_in):
            flash(
                "Public list slug must be 3–42 chars: lowercase letters, digits, and hyphens only.",
                "error",
            )
            return redirect(url_for("account_settings"))
        notify_em = 1 if request.form.get("notify_email_chapters") == "1" else 0
        with get_conn() as conn:
            if slug_in:
                taken = conn.execute(
                    "SELECT id FROM users WHERE lower(public_list_slug) = ? AND id != ?",
                    (slug_in, user_id),
                ).fetchone()
                if taken:
                    flash("That public list slug is already taken.", "error")
                    return redirect(url_for("account_settings"))
            conn.execute(
                """
                UPDATE users
                SET webhook_url = ?, public_list_slug = ?, notify_email_chapters = ?
                WHERE id = ?
                """,
                (wh or None, slug_in or None, notify_em, user_id),
            )
        flash("Settings saved.", "success")
        return redirect(url_for("account_settings"))

    row = None
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT webhook_url, api_access_token, public_list_slug, notify_email_chapters
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    rss_feed_url = None
    try:
        with get_conn() as conn:
            tok = _ensure_user_rss_token(conn, user_id)
        rss_feed_url = url_for("user_rss_feed", token=tok, _external=True)
    except Exception:
        pass

    tok_preview = ""
    raw_tok = (row["api_access_token"] or "").strip() if row else ""
    if raw_tok:
        tok_preview = raw_tok[:6] + "…" + raw_tok[-4:]

    public_url = None
    if row and (row["public_list_slug"] or "").strip():
        try:
            public_url = url_for("public_library", slug=(row["public_list_slug"] or "").strip(), _external=True)
        except Exception:
            public_url = None

    return render_template(
        "account_settings.html",
        current_user=current_user,
        rss_feed_url=rss_feed_url,
        webhook_url=(row["webhook_url"] if row else "") or "",
        public_list_slug=(row["public_list_slug"] if row else "") or "",
        notify_email_chapters=int(row["notify_email_chapters"] or 0) if row else 0,
        api_token_preview=tok_preview,
        public_list_url=public_url,
        demo_mode=False,
        search_q="",
        sort="added",
        page=1,
    )


@app.route("/list/<slug>")
def public_library(slug: str):
    slug_clean = (slug or "").strip().lower()
    if not _public_slug_ok(slug_clean):
        abort(404)
    with get_conn() as conn:
        urow = conn.execute(
            "SELECT id FROM users WHERE lower(public_list_slug) = ?",
            (slug_clean,),
        ).fetchone()
    if not urow:
        abort(404)
    user_id = int(urow["id"])
    raw_rows, raw_by_id = _fetch_user_story_rows(user_id, "")
    story_cards = _build_sorted_story_cards(raw_rows, raw_by_id, "title")
    return render_template("public_list.html", slug=slug_clean, bookmarks=story_cards)


@app.route("/source-requests", methods=["GET", "POST"])
@limiter.limit("12/hour", methods=["POST"], key_func=get_remote_address)
def source_requests_page():
    if request.method == "POST":
        domain = (request.form.get("domain") or "").strip().lower()
        title_hint = (request.form.get("title_hint") or "").strip()
        url_example = (request.form.get("url_example") or "").strip()
        if not domain or not title_hint:
            flash("Domain and title are required.", "error")
        elif len(title_hint) > 200 or len(domain) > 120:
            flash("Inputs are too long.", "error")
        else:
            if url_example and not is_public_http_url(url_example):
                flash("Example URL must be a public http(s) link or empty.", "error")
            else:
                with get_conn() as conn:
                    conn.execute(
                        """
                        INSERT INTO source_requests (domain, title_hint, url_example, created_at, votes)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (domain[:120], title_hint[:200], (url_example or None)[:500] if url_example else None, _now_iso_z(), 1),
                    )
                flash("Request submitted. Thank you.", "success")
                return redirect(url_for("source_requests_page"))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, domain, title_hint, url_example, created_at, votes
            FROM source_requests
            ORDER BY votes DESC, id DESC
            LIMIT 200
            """
        ).fetchall()
    return render_template(
        "source_requests.html",
        rows=rows,
        current_user=get_current_user(),
        demo_mode=False,
        search_q="",
        sort="added",
        page=1,
    )


@app.route("/source-requests/<int:req_id>/vote", methods=["POST"])
@limiter.limit("40/hour", methods=["POST"], key_func=get_remote_address)
def source_requests_vote(req_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE source_requests SET votes = votes + 1 WHERE id = ?", (req_id,))
    flash("Vote recorded.", "info")
    return redirect(url_for("source_requests_page"))


def _record_source_candidate(domain: str, title_hint: str, url_example: str) -> None:
    d = (domain or "").strip().lower()[:120]
    t = (title_hint or "").strip()[:200]
    u = (url_example or "").strip()[:500]
    if not d:
        return
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM source_requests WHERE domain = ?", (d,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE source_requests
                SET votes = votes + 1,
                    title_hint = CASE WHEN title_hint IS NULL OR title_hint = '' THEN ? ELSE title_hint END,
                    url_example = CASE WHEN url_example IS NULL OR url_example = '' THEN ? ELSE url_example END
                WHERE id = ?
                """,
                (t or None, u or None, int(existing["id"])),
            )
            return
        conn.execute(
            """
            INSERT INTO source_requests (domain, title_hint, url_example, created_at, votes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (d, t or d, u or None, _now_iso_z(), 1),
        )


@csrf.exempt
@app.route("/api/import/mal", methods=["POST"])
def api_import_mal_stub():
    return jsonify({"ok": False, "error": "MyAnimeList import is not implemented yet"}), 501


@app.route("/healthz")
def healthz():
    """Liveness probe only: no database, scraping, or scheduler work."""
    resp = jsonify({"ok": True, "status": "healthy"})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/feeds/rss/<token>")
def user_rss_feed(token: str):
    tok = (token or "").strip()
    if not tok:
        abort(404)
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE rss_feed_token = ?", (tok,)).fetchone()
    if not row:
        abort(404)
    user_id = int(row["id"])
    root = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if not root:
        root = request.url_root.rstrip("/")
    body = _render_user_rss_xml(user_id, root)
    resp = Response(body, mimetype="application/rss+xml; charset=utf-8")
    resp.headers["Cache-Control"] = "private, max-age=120"
    return resp


@app.route("/api/registry/public", methods=["GET"])
def api_registry_public():
    snap = source_registry.public_api_snapshot()
    resp = jsonify({"ok": True, **snap})
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


LANDING_TRENDING_DEMO = {
    "trending_now": [
        {"title": "Solo Leveling", "slug": "solo-leveling", "watchers": 1240},
        {"title": "Omniscient Reader", "slug": "omniscient-reader", "watchers": 968},
        {"title": "Blue Lock", "slug": "blue-lock", "watchers": 851},
    ],
    "most_watched": [
        {"title": "Jujutsu Kaisen", "slug": "jujutsu-kaisen", "watchers": 2218},
        {"title": "One Piece", "slug": "one-piece", "watchers": 2144},
        {"title": "Tower of God", "slug": "tower-of-god", "watchers": 1622},
    ],
    "recently_updated": [
        {"title": "Sakamoto Days", "chapter": "Ch. 170"},
        {"title": "Nano Machine", "chapter": "Ch. 229"},
        {"title": "Dandadan", "chapter": "Ch. 192"},
    ],
}

LANDING_SOURCE_PREVIEW = [
    {"source_name": "Asura", "latest": "Ch. 179", "note": "Fast updates", "label": "Supported"},
    {"source_name": "Reaper", "latest": "Ch. 178", "note": "Backup mirror", "label": "Supported"},
    {"source_name": "MangaDex", "latest": "Ch. 200", "note": "Public catalog", "label": "Automatic"},
    {"source_name": "Unknown", "latest": "Manual", "note": "User-added", "label": "Manual"},
]

DEMO_SOURCE_RESULTS = [
    {"sourceName": "Asura", "supportLabel": "Supported", "latestChapter": "179", "confidence": 0.94},
    {"sourceName": "Reaper", "supportLabel": "Supported", "latestChapter": "178", "confidence": 0.88},
    {"sourceName": "MangaDex", "supportLabel": "Official API", "latestChapter": "200", "confidence": 0.96},
    {"sourceName": "Manual", "supportLabel": "Manual", "latestChapter": None, "confidence": 0.42},
]


LANDING_RECENT_UPDATES_DEMO = [
    {"title": "Solo Leveling", "source": "MangaDex", "chapter": "Ch. 200", "status": "Featured example"},
    {"title": "Jujutsu Kaisen", "source": "Manga Plus", "chapter": "Ch. 271", "status": "Featured example"},
    {"title": "Tower of God", "source": "WEBTOON", "chapter": "Ch. 640", "status": "Featured example"},
    {"title": "Omniscient Reader", "source": "Manual", "chapter": "Ch. 257", "status": "Featured example"},
    {"title": "Chainsaw Man", "source": "MangaDex", "chapter": "Ch. 196", "status": "Featured example"},
]


def _landing_series_card(slug: str) -> Optional[dict]:
    from services import discovery

    by_slug = {row["slug"]: row for row in discovery.LOCAL_DISCOVERY_CATALOG}
    raw = by_slug.get(slug)
    if not raw:
        return None
    d = discovery._decorate_series(raw)
    st = (d.get("type") or "manga").strip().lower()
    type_label = "Manhwa" if st == "manhwa" else "Manga"
    return {
        "slug": d["slug"],
        "title": d["title"],
        "type_label": type_label,
        "latest_chapter": d.get("latest_chapter") or "?",
        "sources_found": int(d.get("sources_found") or 0),
        "cover_url": (d.get("cover_url") or "").strip(),
    }


def _landing_cards_for_slugs(slugs: list[str]) -> list[dict]:
    out: list[dict] = []
    for s in slugs:
        row = _landing_series_card(s)
        if row:
            out.append(row)
    return out


def home():
    trending_slugs = [
        "solo-leveling",
        "omniscient-reader",
        "tower-of-god",
        "the-beginning-after-the-end",
        "jujutsu-kaisen",
        "one-piece",
    ]
    manhwa_slugs = [
        "solo-leveling",
        "tower-of-god",
        "omniscient-reader",
        "the-beginning-after-the-end",
        "lookism",
        "eleceed",
    ]
    manga_slugs = [
        "one-piece",
        "jujutsu-kaisen",
        "chainsaw-man",
        "blue-lock",
        "vinland-saga",
        "berserk",
    ]
    return render_template(
        "landing_v2.html",
        trending=LANDING_TRENDING_DEMO,
        source_preview=LANDING_SOURCE_PREVIEW,
        landing_trending_cards=_landing_cards_for_slugs(trending_slugs),
        landing_popular_manhwa=_landing_cards_for_slugs(manhwa_slugs),
        landing_popular_manga=_landing_cards_for_slugs(manga_slugs),
        landing_recent_updates=LANDING_RECENT_UPDATES_DEMO,
        current_user=get_current_user(),
    )


def public_search():
    return redirect(url_for("discover_page", q=(request.args.get("q") or "").strip()))


def discover_page():
    q = (request.args.get("q") or "").strip()
    url_q = (request.args.get("url") or "").strip()
    local = discovery.search_local_series(q) if q else []
    results = local[:8]
    trend = discovery.trending_snapshot()
    resolved = None
    if url_q:
        try:
            preview = source_engine_resolve_url(url_q)
            resolved = asdict(preview)
            resolved["status"] = "supported" if preview.support_level != "manual" else "manual"
            resolved["supportLabel"] = preview.support_level.replace("_", " ").title()
            resolved["chaptersFound"] = len(preview.chapters or [])
        except Exception as exc:
            resolved = {"ok": False, "error": str(exc), "input_url": url_q}
    return render_template(
        "discover.html",
        q=q,
        url_q=url_q,
        results=results,
        trending=trend,
        source_policy=supported_source_policy(),
        resolved=resolved,
        current_user=get_current_user(),
        demo_mode=False,
        search_q=q,
        sort="added",
        page=1,
        check_all_status_text="",
        total_count=0,
    )


def public_series(slug: str):
    safe_slug = (slug or "").strip().lower()[:120]
    row = next((it for it in discovery.search_local_series(safe_slug.replace("-", " ")) if it.get("slug") == safe_slug), None)
    if row is None:
        row = discovery.get_series_by_id(1 if safe_slug == "solo-leveling" else 0)
    return render_template(
        "public_series.html",
        slug=safe_slug,
        title=(row.get("title") if row else safe_slug.replace("-", " ").title()) if safe_slug else "Series",
        source_preview=(row.get("sources") if row else LANDING_SOURCE_PREVIEW),
    )


def about_page():
    return render_template("about.html")


def extension_page():
    return render_template("extension_landing.html", current_user=get_current_user())


register_public_routes(
    app,
    {
        "home": home,
        "public_search": public_search,
        "discover_page": discover_page,
        "public_series": public_series,
        "about_page": about_page,
        "extension_page": extension_page,
    },
)


def index():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        # Session can become stale after deploys or DB resets.
        session.pop("user_id", None)
        return _login_redirect_preserve_destination()

    page_size = BOOKMARKS_PAGE_SIZE
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    search_q = (request.args.get("q") or "").strip()[:200]
    sort = (request.args.get("sort") or "added").strip().lower()
    if sort not in SORT_MODES:
        sort = "added"
    index_link_kw = _index_redirect_kwargs(search_q, sort)
    edit_link_kw = _index_redirect_kwargs(search_q, sort, page)

    raw_rows, raw_by_id = _fetch_user_story_rows(user_id, search_q)
    story_cards = _build_sorted_story_cards(raw_rows, raw_by_id, sort)

    total_count = len(story_cards)
    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * page_size
    bookmarks = story_cards[offset : offset + page_size]

    total_unread = sum(float(c.get("unread_count") or 0) for c in story_cards)
    behind_count = sum(1 for c in story_cards if float(c.get("unread_count") or 0) > 0)
    insights = reading_insights.build_insights(story_cards)

    with CHECK_ALL_STATUS_LOCK:
        check_all_running = CHECK_ALL_RUNNING
        check_all_last_finished_at = CHECK_ALL_LAST_FINISHED_AT
    check_all_status_text = (
        "Check running..."
        if check_all_running
        else f"Last checked: {_format_relative_age(check_all_last_finished_at)}"
    )

    show_onboarding = bool(session.get("onboarding_pending"))
    all_caught_up = total_count > 0 and behind_count == 0

    duplicate_hints = _load_duplicate_hints(user_id, limit=10)
    stale_story_count = 0
    for c in story_cards:
        dd = _days_since_iso_optional(c.get("_last_checked"))
        if dd is not None and dd >= DEAD_SERIES_WARNING_DAYS:
            stale_story_count += 1
    rss_feed_url = None
    try:
        with get_conn() as conn:
            tok = _ensure_user_rss_token(conn, user_id)
        rss_feed_url = url_for("user_rss_feed", token=tok)
    except Exception:
        pass

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
        show_onboarding=show_onboarding,
        all_caught_up=all_caught_up,
        demo_mode=False,
        insights=insights,
        ui_show_source_hosts=UI_SHOW_SOURCE_HOSTS,
        duplicate_hints=duplicate_hints,
        rss_feed_url=rss_feed_url,
        stale_story_count=stale_story_count,
        dead_series_days=DEAD_SERIES_WARNING_DAYS,
    )


@app.route("/app/library")
def app_library():
    return redirect(url_for("index"))


def app_add_url():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        session.pop("user_id", None)
        return _login_redirect_preserve_destination()
    raw_rows, _ = _fetch_user_story_rows(user_id, "")
    total_count = len(raw_rows)
    with CHECK_ALL_STATUS_LOCK:
        check_all_running = CHECK_ALL_RUNNING
        check_all_last_finished_at = CHECK_ALL_LAST_FINISHED_AT
    check_all_status_text = (
        "Check running..."
        if check_all_running
        else f"Last checked: {_format_relative_age(check_all_last_finished_at)}"
    )
    prefill_url = (request.args.get("url") or "").strip()
    prefill_title = (request.args.get("title") or "").strip()
    return render_template(
        "app_add.html",
        current_user=current_user,
        total_count=total_count,
        search_q="",
        sort="added",
        page=1,
        demo_mode=False,
        check_all_status_text=check_all_status_text,
        prefill_url=prefill_url,
        prefill_title=prefill_title,
    )


@app.route("/app/search")
def app_search():
    if not login_required():
        return _login_redirect_preserve_destination()
    return redirect(url_for("public_search", q=(request.args.get("q") or "")))


@app.route("/app/series/<int:series_id>")
def app_series_detail(series_id: int):
    if not login_required():
        return _login_redirect_preserve_destination()
    return render_template(
        "app_series.html",
        series_id=series_id,
        source_preview=LANDING_SOURCE_PREVIEW,
    )


@app.route("/app/requests")
def app_requests():
    if not login_required():
        return _login_redirect_preserve_destination()
    return redirect(url_for("source_requests_page"))


@app.route("/app/settings")
def app_settings():
    if not login_required():
        return _login_redirect_preserve_destination()
    return redirect(url_for("account_settings"))


@app.route("/next")
def next_up():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    current_user = get_current_user()
    if current_user is None:
        session.pop("user_id", None)
        return _login_redirect_preserve_destination()

    raw_rows, raw_by_id = _fetch_user_story_rows(user_id, "")
    if not raw_rows:
        return render_template(
            "next_up.html",
            queue=[],
            current_user=current_user,
            insights={},
            ui_show_source_hosts=UI_SHOW_SOURCE_HOSTS,
            demo_mode=False,
            search_q="",
            sort="added",
            page=1,
        )
    story_cards = _build_sorted_story_cards(raw_rows, raw_by_id, "unread")
    insights = reading_insights.build_insights(story_cards)
    queue = reading_insights.rank_next_up(story_cards, insights)
    return render_template(
        "next_up.html",
        queue=queue,
        current_user=current_user,
        insights=insights,
        ui_show_source_hosts=UI_SHOW_SOURCE_HOSTS,
        demo_mode=False,
        search_q="",
        sort="added",
        page=1,
    )


@app.route("/export", methods=["GET"])
def export_data():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    with get_conn() as conn:
        bookmarks = conn.execute("SELECT * FROM bookmarks WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
        progress = conn.execute("SELECT * FROM reading_progress WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
    payload = {
        "version": 1,
        "exported_at": _now_iso_z(),
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
        return _login_redirect_preserve_destination()
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
            old_id = parse_backup_int(b.get("id"))
            if old_id is None:
                skipped_malformed_bookmarks += 1
                continue
            raw_url = (b.get("url") or "").strip()
            title = (b.get("title") or "").strip()
            if not title or not is_public_http_url(raw_url):
                skipped_invalid_bookmarks += 1
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO bookmarks
                (user_id, title, url, latest_seen, latest_seen_num, latest_seen_url, cover_url, new_update, last_checked, last_error, series_key, story_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    b.get("story_id"),
                    b.get("created_at") or _now_iso_z(),
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
            old_bookmark_id = parse_backup_int(p.get("bookmark_id"))
            if old_bookmark_id is None:
                skipped_malformed_progress += 1
                continue
            mapped_bookmark_id = id_map.get(old_bookmark_id)
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
                    p.get("seen_at") or _now_iso_z(),
                ),
            )
            if getattr(cur, "rowcount", 0) == 1:
                inserted_progress += 1

    pruned = maybe_prune_reading_progress_for_user(user_id)
    with get_conn() as conn:
        _backfill_bookmark_story_ids(conn)

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
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    if not title or not is_public_http_url(url):
        return redirect_index_preserve_search()

    bookmark_id: Optional[int] = None
    sid = story_groups.new_solo_story_id()
    now = _now_iso_z()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO bookmarks (user_id, title, url, cover_url, story_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, url, None, sid, now),
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
        return _login_redirect_preserve_destination()
    check_single(bookmark_id, get_actor_user_id(), force=True)
    return redirect_index_preserve_search()


@app.route("/check-story", methods=["POST"])
def check_story_group():
    """Re-scrape every physical bookmark URL that belongs to the same logical story."""
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    story_id = (request.form.get("story_id") or "").strip()
    if not story_id:
        return redirect_index_preserve_search()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND story_id = ?",
            (user_id, story_id),
        ).fetchall()
    for r in rows:
        check_single(int(r["id"]), user_id, force=True)
    return redirect_index_preserve_search()


@app.route("/check-all", methods=["POST"])
def check_all_route():
    if not login_required():
        return _login_redirect_preserve_destination()
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
                    CHECK_ALL_LAST_FINISHED_AT = datetime.now(timezone.utc)

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
        finished_at = CHECK_ALL_LAST_FINISHED_AT.strftime("%Y-%m-%dT%H:%M:%SZ") if CHECK_ALL_LAST_FINISHED_AT else None
    return jsonify({"ok": True, "running": running, "finished_at": finished_at})


@app.route("/mark-seen/<int:bookmark_id>", methods=["POST"])
def mark_seen(bookmark_id: int):
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("UPDATE bookmarks SET new_update = 0 WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect_index_preserve_search()


@app.route("/mark-all-seen", methods=["POST"])
def mark_all_seen():
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("UPDATE bookmarks SET new_update = 0 WHERE user_id = ?", (user_id,))
    flash("Marked all series as seen — new-update flags cleared for your whole library.", "success")
    return redirect_index_preserve_search()


@app.route("/bookmark/<int:bookmark_id>/read-through", methods=["POST"])
def read_through(bookmark_id: int):
    if not login_required():
        return _login_redirect_preserve_destination()
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
        return _login_redirect_preserve_destination()
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
    sidebar_ctx = {
        "current_user": get_current_user(),
        "demo_mode": False,
        "search_q": return_q,
        "sort": return_sort,
        "page": return_page,
    }
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, url, story_id FROM bookmarks WHERE id = ? AND user_id = ?",
            (bookmark_id, user_id),
        ).fetchone()
        merge_choices = conn.execute(
            """
            SELECT id, title FROM bookmarks
            WHERE user_id = ? AND id != ?
            ORDER BY LOWER(title) ASC
            LIMIT 200
            """,
            (user_id, bookmark_id),
        ).fetchall()
    if not row:
        flash("Series not found.", "error")
        return redirect(url_for("index", **_index_redirect_kwargs(return_q, return_sort, return_page)))
    if request.method == "POST":
        merge_only = (request.form.get("merge_only") or "").strip() == "1"
        merge_with = (request.form.get("merge_with_bookmark_id") or "").strip()
        if merge_only and not merge_with:
            flash("Pick a series to link as an alternate source.", "warning")
            return render_template(
                "edit_bookmark.html",
                bookmark=dict(row),
                merge_choices=merge_choices,
                return_q=return_q,
                return_sort=return_sort,
                return_page=return_page,
                edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
                **sidebar_ctx,
            )
        if merge_with:
            try:
                mid = int(merge_with)
            except ValueError:
                mid = 0
            if mid:
                with get_conn() as conn:
                    other = conn.execute(
                        "SELECT id, story_id FROM bookmarks WHERE id = ? AND user_id = ?",
                        (mid, user_id),
                    ).fetchone()
                    if other and int(other["id"]) != int(bookmark_id):
                        target_sid = (other["story_id"] or "").strip() or story_groups.new_solo_story_id()
                        conn.execute(
                            "UPDATE bookmarks SET story_id = ? WHERE id = ? AND user_id = ?",
                            (target_sid, int(other["id"]), user_id),
                        )
                        conn.execute(
                            "UPDATE bookmarks SET story_id = ? WHERE id = ? AND user_id = ?",
                            (target_sid, bookmark_id, user_id),
                        )
                flash("Linked as an alternate source — your dashboard merges chapter counts across these URLs.", "success")
                return redirect(url_for("index", **_index_redirect_kwargs(return_q, return_sort, return_page)))
        title = request.form.get("title", "").strip()
        url = request.form.get("url", "").strip()
        if not title or not is_public_http_url(url):
            flash("Title and a valid http(s) URL are required.", "error")
            return render_template(
                "edit_bookmark.html",
                bookmark=dict(row),
                merge_choices=merge_choices,
                return_q=return_q,
                return_sort=return_sort,
                return_page=return_page,
                edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
                **sidebar_ctx,
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
                    merge_choices=merge_choices,
                    return_q=return_q,
                    return_sort=return_sort,
                    return_page=return_page,
                    edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
                    **sidebar_ctx,
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
        merge_choices=merge_choices,
        return_q=return_q,
        return_sort=return_sort,
        return_page=return_page,
        edit_back_kw=_index_redirect_kwargs(return_q, return_sort, return_page),
        **sidebar_ctx,
    )


@app.route("/delete/<int:bookmark_id>", methods=["POST"])
def delete_bookmark(bookmark_id: int):
    if not login_required():
        return _login_redirect_preserve_destination()
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect_index_preserve_search()


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
    try:
        profile = source_registry.get_profile_for_url(canonical_url)
    except Exception:
        profile = None
    if not profile:
        host = urlparse(canonical_url).netloc.lower().replace("www.", "").split(":")[0].strip(".")
        _record_source_candidate(host, title, canonical_url)
    cover_url = scrape_series_cover(canonical_url, title)
    sk_norm = series_key.strip().lower() if series_key else ""
    story_ident = story_groups.story_id_from_series_key(sk_norm) if sk_norm else story_groups.new_solo_story_id()
    with get_conn() as conn:
        existing = None
        if series_key:
            existing = conn.execute(
                "SELECT id, title, url, series_key, story_id FROM bookmarks WHERE user_id = ? AND series_key = ?",
                (user_id, series_key),
            ).fetchone()
        if existing is None:
            existing = conn.execute(
                "SELECT id, title, url, series_key, story_id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, canonical_url),
            ).fetchone()

        if existing is not None:
            created = False
            row = existing
            if cover_url:
                conn.execute("UPDATE bookmarks SET cover_url = COALESCE(cover_url, ?) WHERE id = ?", (cover_url, row["id"]))
            if sk_norm:
                conn.execute("UPDATE bookmarks SET series_key = ?, story_id = ? WHERE id = ?", (sk_norm, story_ident, row["id"]))
            row = conn.execute(
                "SELECT id, title, url, series_key, cover_url, story_id FROM bookmarks WHERE id = ?",
                (row["id"],),
            ).fetchone()
        else:
            now = _now_iso_z()
            cursor = conn.execute(
                "INSERT OR IGNORE INTO bookmarks (user_id, title, url, series_key, cover_url, story_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, title, canonical_url, series_key or None, cover_url, story_ident, now),
            )
            created = cursor.rowcount == 1
            row = conn.execute(
                "SELECT id, title, url, series_key, cover_url, story_id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, canonical_url),
            ).fetchone()
            if row is None:
                return jsonify({"ok": False, "error": "series URL already exists under another local account"}), 409
    return jsonify({"ok": True, "created": created, "series": dict(row)})


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
                    _now_iso_z(),
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
                   b.story_id AS story_id,
                   b.title AS title,
                   b.series_key AS series_key,
                   b.url AS url,
                   b.latest_seen_num AS latest_num,
                   b.latest_seen AS latest_seen,
                   b.latest_seen_url AS latest_seen_url,
                   b.new_update AS new_update,
                   rp.chapter_num AS read_num,
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
            """,
            (user_id, user_id, user_id),
        ).fetchall()

    mapped = []
    tracked_keys: list[str] = []
    tracked_url_norms: list[str] = []
    for row in rows:
        sk = row["series_key"]
        if sk:
            tracked_keys.append(sk)
        raw_url = (row["url"] or "").strip()
        if raw_url:
            tracked_url_norms.append(normalize_bookmark_url(raw_url))
        mapped.append(
            {
                "id": int(row["bookmark_id"]),
                "story_id": row["story_id"],
                "title": row["title"],
                "series_key": sk,
                "url": row["url"],
                "latest_seen_num": row["latest_num"],
                "latest_seen": row["latest_seen"],
                "latest_seen_url": row["latest_seen_url"],
                "read_chapter_num": row["read_num"],
                "read_chapter_label": row["read_chapter_label"],
                "read_source_url": row["read_source_url"],
                "new_update": row["new_update"],
                "cover_url": None,
                "last_error": None,
                "latest_parser_version": None,
            }
        )
    cards = story_groups.group_and_aggregate(mapped)
    total_unread = sum(float(c.get("unread_count") or 0) for c in cards)
    behind_count = sum(1 for c in cards if float(c.get("unread_count") or 0) > 0)
    series = []
    for c in cards:
        ur = float(c.get("unread_count") or 0)
        if ur <= 0:
            continue
        series.append(
            {
                "bookmark_id": c["id"],
                "title": c["title"],
                "series_key": c.get("series_key"),
                "story_id": c.get("story_id"),
                "unread": int(ur) if ur.is_integer() else round(ur, 1),
            }
        )

    return jsonify(
        {
            "ok": True,
            "unread": int(total_unread) if float(total_unread).is_integer() else round(total_unread, 1),
            "behind": behind_count,
            "series": series,
            "tracked_keys": tracked_keys,
            "tracked_url_norms": tracked_url_norms,
        }
    )


@app.route("/api/library/duplicate-hints", methods=["GET"])
def api_duplicate_hints():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    hints = _load_duplicate_hints(user_id, limit=40)
    return jsonify({"ok": True, "hints": hints})


@csrf.exempt
@app.route("/api/library/merge-bookmarks", methods=["POST"])
def api_merge_bookmarks():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        keeper_id = int(payload.get("keeper_id") or 0)
    except (TypeError, ValueError):
        keeper_id = 0
    raw_ids = payload.get("merge_ids") or payload.get("other_ids") or []
    other_ids: list[int] = []
    for x in raw_ids:
        try:
            oid = int(x)
        except (TypeError, ValueError):
            continue
        if oid != keeper_id:
            other_ids.append(oid)
    if keeper_id <= 0 or not other_ids:
        return jsonify({"ok": False, "error": "keeper_id and merge_ids required"}), 400

    target_sid: str = ""
    with get_conn() as conn:
        k = conn.execute(
            "SELECT id, story_id FROM bookmarks WHERE id = ? AND user_id = ?",
            (keeper_id, user_id),
        ).fetchone()
        if not k:
            return jsonify({"ok": False, "error": "keeper not found"}), 404
        target_sid = (k["story_id"] or "").strip() or story_groups.new_solo_story_id()
        conn.execute(
            "UPDATE bookmarks SET story_id = ? WHERE id = ? AND user_id = ?",
            (target_sid, keeper_id, user_id),
        )
        for oid in other_ids:
            o = conn.execute(
                "SELECT id FROM bookmarks WHERE id = ? AND user_id = ?",
                (oid, user_id),
            ).fetchone()
            if not o:
                continue
            conn.execute(
                "UPDATE bookmarks SET story_id = ? WHERE id = ? AND user_id = ?",
                (target_sid, oid, user_id),
            )
    return jsonify({"ok": True, "story_id": target_sid})


@app.route("/api/library/chapter-map", methods=["GET"])
def api_chapter_map():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    raw_rows, _raw_by_id = _fetch_user_story_rows(user_id, "")
    by_sid: dict[str, list[dict]] = defaultdict(list)
    for r in raw_rows:
        d = dict(r)
        sid = story_groups.effective_story_id(d)
        host = urlparse((d.get("url") or "").strip()).netloc.replace("www.", "")
        by_sid[sid].append(
            {
                "bookmark_id": int(d["id"]),
                "title": d.get("title"),
                "url": d.get("url"),
                "host": host,
                "latest_seen_num": d.get("latest_seen_num"),
                "last_checked": d.get("last_checked"),
                "last_error": d.get("last_error"),
            }
        )
    stories_out = [{"story_id": k, "sources": v} for k, v in by_sid.items()]
    stories_out.sort(key=lambda x: x["story_id"])
    return jsonify({"ok": True, "stories": stories_out})


@app.route("/api/library/alt-sources", methods=["GET"])
def api_alt_sources():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    raw = (request.args.get("url") or "").strip()
    if not raw or not is_public_http_url(raw):
        return jsonify({"ok": False, "error": "valid url required"}), 400
    prof = source_registry.get_profile_for_url(raw)
    curr_id = (prof or {}).get("id")
    health = source_registry.load_health()
    by_h = health.get("by_id") if isinstance(health.get("by_id"), dict) else {}
    alternatives: list[dict] = []
    for src in source_registry.list_public_sources():
        if curr_id and src.get("id") == curr_id:
            continue
        hid = src.get("id")
        row = by_h.get(hid) if hid else {}
        st = str((row or {}).get("check_status") or (row or {}).get("status") or "partial").lower()
        if st == "broken":
            continue
        alternatives.append(
            {
                "id": hid,
                "display_name": src.get("display_name"),
                "domains": src.get("domains"),
                "sample_series_url": src.get("sample_series_url"),
                "health_status": st,
            }
        )
    return jsonify({"ok": True, "current_source_id": curr_id, "alternatives": alternatives[:40]})


def api_resolve_url():
    data = request.get_json(silent=True) or {}
    raw_url = (data.get("url") or "").strip()[: RESOLVE_URL_MAX_LEN + 1]
    if not raw_url:
        return jsonify({"ok": False, "error": "url is required"}), 400
    if len(raw_url) > RESOLVE_URL_MAX_LEN:
        return jsonify({"ok": False, "error": "url is too long"}), 400
    raw_parsed = urlparse(raw_url)
    if raw_parsed.scheme and raw_parsed.scheme not in ("http", "https"):
        return jsonify({"ok": False, "error": "url must use http or https"}), 400
    try:
        normalized = source_engine_normalize_url(raw_url)
    except Exception:
        return jsonify({"ok": False, "error": "invalid url"}), 400
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"ok": False, "error": "url must use http or https"}), 400
    if not is_public_http_url(normalized):
        return jsonify({"ok": False, "error": "url must be a public http(s) address"}), 400

    cached = _cache_get(_RESOLVE_CACHE, normalized, RESOLVE_CACHE_TTL_SECONDS)
    if cached is not None:
        return jsonify(cached)
    try:
        preview = source_engine_resolve_url(normalized)
    except Exception:
        fallback = {
            "ok": True,
            "status": "manual",
            "support_level": "manual_only",
            "supportLabel": "Manual Only",
            "source_name": "Manual",
            "source_url": normalized,
            "title": "",
            "chaptersFound": 0,
            "warnings": ["Automatic detection failed. Manual tracking is available."],
        }
        _cache_set(_RESOLVE_CACHE, normalized, fallback)
        return jsonify(fallback)
    payload = asdict(preview)
    payload["status"] = "supported" if preview.support_level not in ("manual_only", "blocked") else "manual"
    payload["supportLabel"] = preview.support_level.replace("_", " ").title()
    payload["chaptersFound"] = len(preview.chapters or [])
    payload["ok"] = True
    if payload.get("support_level") == "manual_only":
        warnings = list(payload.get("warnings") or [])
        warnings.append("Automatic detection is unavailable for this URL. You can still track it manually.")
        payload["warnings"] = warnings
    _cache_set(_RESOLVE_CACHE, normalized, payload)
    return jsonify(payload)


@csrf.exempt
@app.route("/api/track", methods=["POST"])
def api_track_series():
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "status": "queued", "series": data.get("series") or data.get("title") or "series"})


@app.route("/api/search", methods=["GET"])
def api_public_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"ok": True, "items": []})
    return jsonify(
        {
            "ok": True,
            "items": [
                {"title": q.title(), "slug": re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-"), "foundOn": 5, "recommended": "Asura"}
            ],
        }
    )


@app.route("/api/series/<int:series_id>/sources", methods=["GET"])
def api_series_sources(series_id: int):
    return jsonify({"ok": True, "seriesId": series_id, "sources": LANDING_SOURCE_PREVIEW})


@csrf.exempt
@app.route("/api/source-request", methods=["POST"])
def api_source_request():
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()[:255]
    if not domain:
        return jsonify({"ok": False, "error": "domain is required"}), 400
    return jsonify({"ok": True, "status": "requested", "domain": domain})


def api_trending():
    return jsonify({"ok": True, "is_demo": True, **LANDING_TRENDING_DEMO})


@app.route("/api/recent-updates", methods=["GET"])
def api_recent_updates():
    return jsonify({"ok": True, "items": LANDING_TRENDING_DEMO["recently_updated"]})


@app.route("/api/discover/supported-sources", methods=["GET"])
def api_discover_supported_sources():
    return jsonify({"ok": True, "tiers": supported_source_policy()})


@app.route("/api/discover/search", methods=["GET"])
def api_discover_search():
    q = (request.args.get("q") or "").strip()[:DISCOVER_QUERY_MAX_LEN]
    if not q:
        return jsonify({"ok": True, "items": []})
    items = discovery.search_local_series(q)
    return jsonify({"ok": True, "items": items})


@app.route("/api/discover/series/<int:series_id>", methods=["GET"])
def api_discover_series(series_id: int):
    row = discovery.get_series_by_id(series_id)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "series": row})


@app.route("/api/discover/series/<int:series_id>/sources", methods=["GET"])
def api_discover_series_sources(series_id: int):
    row = discovery.get_series_by_id(series_id)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "series_id": series_id, "sources": row.get("sources", [])})


def api_discover_search_live():
    data = request.get_json(silent=True) or {}
    q = (data.get("q") or "").strip()[:DISCOVER_QUERY_MAX_LEN]
    if not q:
        return jsonify({"ok": False, "error": "q is required"}), 400
    cached = _cache_get(_DISCOVER_LIVE_CACHE, q.lower(), 60)
    if cached is not None:
        return jsonify(cached)
    live = source_engine_search_title(q)
    merged = discovery.merge_live_results(live)
    payload = {"ok": True, "items": merged, "sources_checked": len(live)}
    _cache_set(_DISCOVER_LIVE_CACHE, q.lower(), payload)
    return jsonify(payload)


register_api_discovery_routes(
    app,
    {
        "api_resolve_url": api_resolve_url,
        "api_discover_search_live": api_discover_search_live,
        "api_trending": api_trending,
    },
    csrf=csrf,
    limiter=limiter,
    rate_limit_key_func=_api_v1_rate_limit_key,
)


@csrf.exempt
@app.route("/api/tracker/add-series", methods=["POST"])
def api_tracker_add_series():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    data = request.get_json(silent=True) or {}
    series_id = int(data.get("series_id") or 0)
    mode = (data.get("mode") or "recommended").strip().lower()
    manual_url = (data.get("manual_url") or "").strip()
    manual_title = (data.get("manual_title") or "").strip()[:220]
    if mode == "manual":
        if not manual_url or not is_public_http_url(manual_url):
            return jsonify({"ok": False, "error": "valid manual_url is required"}), 400
        canonical_url = resolve_series_listing_url(manual_url)
        title = manual_title or "Manual series"
        now = _now_iso_z()
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO bookmarks (user_id, title, url, cover_url, story_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, title, canonical_url, "", story_groups.new_solo_story_id(), now),
            )
        return jsonify({"ok": True, "mode": mode, "added": [{"source": "Manual", "url": canonical_url}]})
    row = discovery.get_series_by_id(series_id)
    if not row:
        return jsonify({"ok": False, "error": "series not found"}), 404
    sources = row.get("sources") or []
    if not sources:
        return jsonify({"ok": False, "error": "no sources available"}), 400
    selected = sources[:1] if mode == "recommended" else [s for s in sources if s.get("health_status") == "working"]
    added = []
    with get_conn() as conn:
        for src in selected:
            src_url = (src.get("url") or "").strip()
            if not src_url:
                continue
            if not is_public_http_url(src_url):
                continue
            canonical_url = resolve_series_listing_url(src_url)
            now = _now_iso_z()
            conn.execute(
                "INSERT OR IGNORE INTO bookmarks (user_id, title, url, cover_url, story_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, row.get("title"), canonical_url, row.get("cover_url"), story_groups.new_solo_story_id(), now),
            )
            added.append({"source": src.get("source_name"), "url": canonical_url})
    return jsonify({"ok": True, "mode": mode, "added": added})


def api_library_add_from_preview():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    data = request.get_json(silent=True) or {}
    raw_url = (data.get("url") or "").strip()
    if not raw_url:
        return jsonify({"ok": False, "error": "url is required"}), 400
    if len(raw_url) > RESOLVE_URL_MAX_LEN:
        return jsonify({"ok": False, "error": "url is too long"}), 400
    if not is_public_http_url(raw_url):
        return jsonify({"ok": False, "error": "valid public http(s) url required"}), 400
    support_level = (data.get("support_level") or "manual_only").strip().lower()
    title = (data.get("title") or "").strip()[:220]
    canonical_title = (data.get("canonical_title") or "").strip()[:220]
    description = (data.get("description") or "").strip()[:2000]
    cover_url = (data.get("cover_url") or "").strip()
    if cover_url and not is_public_http_url(cover_url):
        cover_url = ""
    chapter_count_raw = data.get("chapter_count")
    try:
        chapter_count = int(chapter_count_raw) if chapter_count_raw not in (None, "") else None
    except (TypeError, ValueError):
        chapter_count = None
    if chapter_count is not None and chapter_count < 0:
        chapter_count = None
    latest_chapter_raw = str(data.get("latest_chapter") or "").strip()
    if support_level == "manual_only" and not title:
        return jsonify({"ok": False, "error": "title is required for manual tracking"}), 400
    canonical_url = resolve_series_listing_url(raw_url)
    norm = normalize_bookmark_url(canonical_url)
    with get_conn() as conn:
        existing_rows = conn.execute(
            "SELECT id, title, url FROM bookmarks WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        existing = None
        for row in existing_rows:
            if normalize_bookmark_url(row["url"]) == norm:
                existing = row
                break
        if existing is not None:
            return jsonify({"ok": True, "created": False, "duplicate": True, "series": dict(existing)})
        add_title = title or canonical_title or extract_series_slug(canonical_url).replace("-", " ").title() or "Untitled series"
        now = _now_iso_z()
        sid = story_groups.new_solo_story_id()
        conn.execute(
            """
            INSERT OR IGNORE INTO bookmarks
            (user_id, title, canonical_title, description, chapter_count, url, cover_url, story_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, add_title, canonical_title or None, description or None, chapter_count, canonical_url, cover_url or "", sid, now),
        )
        row = conn.execute(
            "SELECT id, title, canonical_title, description, chapter_count, url, cover_url FROM bookmarks WHERE user_id = ? AND url = ?",
            (user_id, canonical_url),
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "failed to add series"}), 500
        if latest_chapter_raw:
            try:
                latest_num = float(latest_chapter_raw)
            except ValueError:
                latest_num = None
            if latest_num is not None and math.isfinite(latest_num) and latest_num >= 0:
                conn.execute(
                    "UPDATE bookmarks SET latest_seen_num = ?, latest_seen = ?, latest_seen_url = ?, last_checked = ? WHERE id = ?",
                    (latest_num, f"Ch {latest_chapter_raw}", canonical_url, now, int(row["id"])),
                )
    return jsonify({"ok": True, "created": True, "duplicate": False, "series": dict(row)})


register_library_routes(
    app,
    {
        "index": index,
        "app_add_url": app_add_url,
        "api_library_add_from_preview": api_library_add_from_preview,
        "ensure_series": ensure_series,
        "save_progress": save_progress,
    },
    csrf=csrf,
)


@csrf.exempt
@app.route("/api/v1/bookmarks", methods=["GET"])
@limiter.limit("60/minute", methods=["GET"], key_func=_api_v1_rate_limit_key)
def api_v1_bookmarks():
    auth = (request.headers.get("Authorization") or "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    user_id = _user_id_from_bearer_api_token(token)
    if user_id is None:
        return jsonify({"ok": False, "error": "invalid or missing bearer token"}), 401
    raw_rows, raw_by_id = _fetch_user_story_rows(user_id, "")
    cards = _build_sorted_story_cards(raw_rows, raw_by_id, "added")
    out = []
    for c in cards:
        out.append(
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "story_id": c.get("story_id"),
                "url": c.get("url"),
                "latest_seen": c.get("latest_seen"),
                "latest_seen_num": c.get("latest_seen_num"),
                "latest_seen_url": c.get("latest_seen_url"),
                "read_chapter_num": c.get("read_chapter_num"),
                "unread_count": c.get("unread_count"),
                "new_update": c.get("new_update"),
                "source_count": c.get("source_count"),
            }
        )
    return jsonify({"ok": True, "bookmarks": out})


@csrf.exempt
@app.route("/api/account/api-token", methods=["POST"])
def api_account_issue_token():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    tok = secrets.token_urlsafe(24)
    with get_conn() as conn:
        conn.execute("UPDATE users SET api_access_token = ? WHERE id = ?", (tok, user_id))
    return jsonify({"ok": True, "token": tok, "usage": "Authorization: Bearer <token> on GET /api/v1/bookmarks"})


@csrf.exempt
@app.route("/api/reader-overlay", methods=["GET"])
def api_reader_overlay():
    user_id = api_session_user_id()
    if user_id is None:
        return jsonify({"ok": False, "error": "authentication required"}), 401
    series_url = (request.args.get("series_url") or "").strip()
    series_key = (request.args.get("series_key") or "").strip().lower()
    page_url = (request.args.get("page_url") or "").strip()
    probe_url = page_url or series_url
    registry_supported = bool(source_registry.get_profile_for_url(probe_url)) if probe_url else False

    canonical: Optional[str] = None
    if series_url and is_public_http_url(series_url):
        try:
            canonical = resolve_series_listing_url(series_url)
        except Exception:
            canonical = series_url

    with get_conn() as conn:
        row = None
        if series_key:
            row = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id = ? AND lower(trim(coalesce(series_key, ''))) = ?",
                (user_id, series_key),
            ).fetchone()
        if row is None and canonical:
            row = conn.execute(
                "SELECT * FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, canonical),
            ).fetchone()
        if row is None and canonical:
            cand_norm = normalize_bookmark_url(canonical)
            for candidate in conn.execute("SELECT * FROM bookmarks WHERE user_id = ?", (user_id,)).fetchall():
                if normalize_bookmark_url(candidate["url"] or "") == cand_norm:
                    row = candidate
                    break

        if row is None:
            return jsonify(
                {
                    "ok": True,
                    "tracked": False,
                    "registry_supported": registry_supported,
                    "series_url": canonical or series_url or "",
                    "series_key": series_key or None,
                }
            )

        bookmark_id = int(row["id"])
        prog = conn.execute(
            """
            SELECT x.chapter_num, x.chapter_label, x.source_url
            FROM reading_progress x
            INNER JOIN (
                SELECT bookmark_id, MAX(id) AS max_id
                FROM reading_progress
                WHERE user_id = ?
                GROUP BY bookmark_id
            ) y ON y.bookmark_id = x.bookmark_id AND y.max_id = x.id
            WHERE x.user_id = ? AND x.bookmark_id = ?
            """,
            (user_id, user_id, bookmark_id),
        ).fetchone()

    read_num: Optional[float] = None
    if prog and prog["chapter_num"] is not None:
        try:
            read_num = float(prog["chapter_num"])
        except (TypeError, ValueError):
            read_num = None
    read_lbl = (prog["chapter_label"] if prog else None) or None
    read_url = (prog["source_url"] if prog else None) or None

    latest_f: Optional[float] = None
    if row["latest_seen_num"] is not None:
        try:
            latest_f = float(row["latest_seen_num"])
        except (TypeError, ValueError):
            latest_f = None
    new_update = int(row["new_update"] or 0)
    unread = 0.0
    if latest_f is not None and read_num is not None:
        unread = max(0.0, float(latest_f) - float(read_num))
    elif latest_f is not None and read_num is None and new_update:
        try:
            unread = max(0.0, float(latest_f))
        except (TypeError, ValueError):
            pass

    continue_url = (read_url or "").strip() or (row["url"] or "")

    return jsonify(
        {
            "ok": True,
            "tracked": True,
            "registry_supported": registry_supported,
            "bookmark_id": bookmark_id,
            "title": row["title"],
            "series_key": row["series_key"],
            "series_url": row["url"],
            "read_chapter_num": read_num,
            "read_chapter_label": read_lbl,
            "latest_seen_num": latest_f,
            "latest_seen": row["latest_seen"],
            "latest_seen_url": row["latest_seen_url"],
            "continue_url": continue_url,
            "unread": int(unread) if float(unread).is_integer() else round(unread, 1),
            "new_update": new_update,
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
    if not is_public_http_url(raw_url):
        return jsonify({"ok": False, "error": "blocked URL"}), 400

    resolved_url = resolve_series_listing_url(raw_url)
    if not is_public_http_url(resolved_url):
        return jsonify({"ok": False, "error": "blocked URL"}), 400
    try:
        res = fetch_public_url(resolved_url, timeout=25)
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


@app.route("/admin/users", methods=["GET"])
def admin_users():
    if not admin_view_authorized():
        if not login_required():
            return _login_redirect_preserve_destination()
        return abort(403)
    with get_conn() as conn:
        totals = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM users) AS total_users,
                (SELECT COUNT(*) FROM bookmarks) AS total_bookmarks,
                (SELECT COUNT(*) FROM reading_progress) AS total_progress
            """
        ).fetchone()
        users = conn.execute(
            """
            SELECT
                u.id,
                u.username,
                u.email,
                u.created_at,
                (SELECT COUNT(*) FROM bookmarks b WHERE b.user_id = u.id) AS bookmark_count,
                (SELECT COUNT(*) FROM reading_progress rp WHERE rp.user_id = u.id) AS progress_count
            FROM users u
            ORDER BY u.created_at DESC, u.id DESC
            """
        ).fetchall()
        latest_users = conn.execute(
            """
            SELECT id, username, email, created_at
            FROM users
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """
        ).fetchall()
        latest_bookmarks = conn.execute(
            """
            SELECT b.id, b.title, b.url, b.created_at, b.user_id, u.username
            FROM bookmarks b
            LEFT JOIN users u ON u.id = b.user_id
            ORDER BY b.created_at DESC, b.id DESC
            LIMIT 10
            """
        ).fetchall()
    return render_template(
        "admin_users.html",
        totals=totals,
        users=users,
        latest_users=latest_users,
        latest_bookmarks=latest_bookmarks,
        admin_link_kw=_admin_link_kw(),
    )


@app.route("/admin/users/<int:user_id>", methods=["GET"])
def admin_user_detail(user_id: int):
    if not admin_view_authorized():
        if not login_required():
            return _login_redirect_preserve_destination()
        return abort(403)
    with get_conn() as conn:
        user = conn.execute(
            "SELECT id, username, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            abort(404)
        bookmarks = conn.execute(
            """
            SELECT id, title, url, latest_seen, latest_seen_num, new_update, created_at
            FROM bookmarks
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
        progress = conn.execute(
            """
            SELECT
                rp.id,
                rp.bookmark_id,
                rp.chapter_num,
                rp.chapter_label,
                rp.source_url,
                rp.seen_at,
                b.title AS bookmark_title
            FROM reading_progress rp
            LEFT JOIN bookmarks b ON b.id = rp.bookmark_id
            WHERE rp.user_id = ?
            ORDER BY rp.seen_at DESC, rp.id DESC
            LIMIT 300
            """,
            (user_id,),
        ).fetchall()
    return render_template(
        "admin_user_detail.html",
        user=user,
        bookmarks=bookmarks,
        progress=progress,
        admin_link_kw=_admin_link_kw(),
    )


@app.route("/admin/source-registry-status", methods=["GET"])
def admin_source_registry_status():
    if not admin_view_authorized():
        if not login_required():
            return _login_redirect_preserve_destination()
        return abort(403)
    rows = source_registry.sources_with_health()
    rows = sorted(rows, key=lambda r: ((r.get("registry_origin") or "zzz"), r.get("display_name") or r.get("id") or ""))
    return render_template(
        "admin_source_registry_status.html",
        rows=rows,
        admin_link_kw=_admin_link_kw(),
    )


def _scheduled_source_health() -> None:
    try:
        from services import source_health_job

        source_health_job.run_and_write_health(print_summary=False)
    except Exception:
        log.exception("source catalog health job failed")


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
        health_hours = int(os.getenv("SOURCE_HEALTH_INTERVAL_HOURS", "24"))
        if health_hours > 0:
            scheduler.add_job(
                _scheduled_source_health,
                "interval",
                hours=max(health_hours, 1),
                id="source-catalog-health",
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

import os
import re
import sqlite3
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, Response
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

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except Exception:
    webdriver = None
    Options = None

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CHAPTER_PATTERN = re.compile(r"(chapter|ch\.?|ep\.?|episode)\s*[:#-]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
URL_CHAPTER_PATTERN = re.compile(r"(?:^|[^a-z])(c|chapter|ch|episode|ep)[-_ ]?(\d+(?:\.\d+)?)$", re.IGNORECASE)
URL_CHAPTER_STEP_PATTERN = re.compile(r"^(chapter|ch|episode|ep)$", re.IGNORECASE)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
MAX_CHECK_WORKERS = max(1, int(os.getenv("MAX_CHECK_WORKERS", "6")))
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "local@tracker")
APP_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
DB_READY = False
REQUIRE_API_AUTH = os.getenv("REQUIRE_API_AUTH", "0") == "1"
CORS_ALLOW_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if not APP_DEBUG and not os.getenv("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set in production")

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
    elif origin.startswith("chrome-extension://"):
        allow_origin = True
    elif APP_DEBUG and (origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")):
        allow_origin = True
    if allow_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.before_request
def handle_preflight():
    global DB_READY
    if not DB_READY:
        init_db()
        DB_READY = True
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
    indexes = conn.execute("PRAGMA index_list(bookmarks)").fetchall()
    for idx in indexes:
        # sqlite3.Row behaves like mapping; PostgreSQL does not use this branch.
        unique = int(idx["unique"]) if "unique" in idx.keys() else 0
        if unique != 1:
            continue
        idx_name = idx["name"]
        safe_name = str(idx_name).replace('"', '""')
        cols = conn.execute(f'PRAGMA index_info("{safe_name}")').fetchall()
        col_names = [c["name"] for c in cols if c["name"]]
        if col_names == ["url"]:
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
                (DEFAULT_USER_EMAIL, generate_password_hash("local-only"), now),
            )
            conn.execute(
                "UPDATE users SET username = COALESCE(username, split_part(email, '@', 1)) WHERE username IS NULL"
            )
            default_user = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USER_EMAIL,)).fetchone()
            default_user_id = default_user["id"]
            conn.execute("UPDATE bookmarks SET user_id = ? WHERE user_id IS NULL", (default_user_id,))
            conn.execute("UPDATE reading_progress SET user_id = ? WHERE user_id IS NULL", (default_user_id,))
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
            (DEFAULT_USER_EMAIL, generate_password_hash("local-only"), now),
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


def parse_chapter_number(text: str) -> Optional[float]:
    match = CHAPTER_PATTERN.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(2))
    except ValueError:
        return None


def parse_chapter_from_url(url: str) -> Optional[float]:
    raw_url = (url or "").strip()
    if not raw_url:
        return None
    path = raw_url
    if "://" in raw_url:
        try:
            from urllib.parse import urlparse

            path = urlparse(raw_url).path
        except Exception:
            path = raw_url
    tokens = [t for t in path.strip("/").split("/") if t]
    if not tokens:
        return None

    # Pattern: /.../chapter/39 or /.../ep/12.5
    if len(tokens) >= 2 and URL_CHAPTER_STEP_PATTERN.match(tokens[-2]):
        try:
            return float(tokens[-1])
        except ValueError:
            pass

    # Pattern: /.../c156 or /.../chapter-156
    tail = tokens[-1]
    match = URL_CHAPTER_PATTERN.search(tail)
    if not match:
        # Fallback for mixed separators in full path.
        match = re.search(r"(?:chapter|ch|episode|ep)[^0-9]{0,3}(\d+(?:\.\d+)?)", path, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    try:
        return float(match.group(2))
    except ValueError:
        return None


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


def api_auth_required() -> bool:
    return not REQUIRE_API_AUTH or login_required()


def scrape_series_cover(url: str, series_title: str = "") -> Optional[str]:
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
    try:
        from urllib.parse import urlparse

        path = urlparse(raw_url).path.strip("/")
    except Exception:
        path = (raw_url or "").strip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    if parts[0].lower() in {"manga", "comics"} and len(parts) >= 2:
        slug = parts[1]
    else:
        slug = parts[-1]
    slug = re.sub(r"-chapter-\d+(?:\.\d+)?$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]\d+(?:\.\d+)?$", "", slug, flags=re.IGNORECASE)
    return slug.lower()


def iter_chapter_candidates(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str, str]]:
    """Return chapter candidates as (label, absolute_url, class_text)."""
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    # Common case: direct chapter links.
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        abs_href = urljoin(page_url, href)
        label = a.get_text(" ", strip=True) or ""
        class_text = " ".join(a.get("class", [])) if a.get("class") else ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, class_text))

    # Some readers render chapter list in <select><option value="...">.
    for opt in soup.select("option[value]"):
        value = (opt.get("value") or "").strip()
        if not value or value.startswith("#"):
            continue
        abs_href = urljoin(page_url, value)
        label = opt.get_text(" ", strip=True) or ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, "option"))

    # Fallback: data attributes often hold chapter URLs.
    for node in soup.select("[data-href], [data-url], [data-link]"):
        raw = (node.get("data-href") or node.get("data-url") or node.get("data-link") or "").strip()
        if not raw:
            continue
        abs_href = urljoin(page_url, raw)
        label = node.get_text(" ", strip=True) or ""
        class_text = " ".join(node.get("class", [])) if node.get("class") else ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, class_text))

    return out


def pick_best_candidate_with_debug(soup: BeautifulSoup, page_url: str) -> dict:
    page_slug = extract_series_slug(page_url)
    best_label: Optional[str] = None
    best_num: Optional[float] = None
    best_url: Optional[str] = None
    best_score = -1
    parser_hits = {"anchors": 0, "options": 0, "data_attrs": 0}
    candidate_debug: list[dict] = []
    error_flags: list[str] = []

    for text, absolute_href, class_text in iter_chapter_candidates(soup, page_url):
        if "option" in class_text:
            parser_hits["options"] += 1
        elif "data-" in class_text:
            parser_hits["data_attrs"] += 1
        else:
            parser_hits["anchors"] += 1

        if not text or len(text) > 140:
            continue
        parsed_from_text = parse_chapter_number(text)
        parsed_from_url = parse_chapter_from_url(absolute_href)
        if parsed_from_text is None and parsed_from_url is None:
            continue

        final_num = parsed_from_text if parsed_from_text is not None else parsed_from_url
        if final_num is None:
            continue

        href_slug = extract_series_slug(absolute_href) if absolute_href else ""
        score = 0
        if parsed_from_url is not None:
            score += 3
        if re.search(r"chapter|episode|list|item", class_text, re.IGNORECASE):
            score += 2
        if page_slug and href_slug:
            if page_slug == href_slug or page_slug in absolute_href.lower():
                score += 5
            else:
                continue
        score += int(final_num)

        candidate_debug.append(
            {
                "label": text,
                "url": absolute_href,
                "chapter_num": final_num,
                "score": score,
                "same_series": bool(not page_slug or (href_slug and (href_slug == page_slug or page_slug in absolute_href.lower()))),
            }
        )

        if score > best_score or (score == best_score and (best_num is None or final_num > best_num)):
            best_score = score
            best_label = text
            best_num = final_num
            best_url = absolute_href or None

    if not candidate_debug:
        error_flags.append("no_chapter_candidates")
    elif len(candidate_debug) > 400:
        error_flags.append("high_candidate_volume")

    confidence = 0.0
    if best_num is not None:
        confidence = 0.55
        if best_url and page_slug and page_slug in best_url.lower():
            confidence += 0.2
        if candidate_debug:
            top_scores = sorted([c["score"] for c in candidate_debug], reverse=True)
            if len(top_scores) == 1:
                confidence += 0.2
            else:
                gap = top_scores[0] - top_scores[1]
                if gap >= 6:
                    confidence += 0.2
                elif gap >= 3:
                    confidence += 0.12
                else:
                    confidence += 0.05
        if best_url and parse_chapter_from_url(best_url) is not None:
            confidence += 0.08
    confidence = max(0.0, min(0.99, round(confidence, 2)))

    if parser_hits["options"] > 0:
        parser_version = "generic-option-list"
    elif parser_hits["data_attrs"] > 0:
        parser_version = "generic-data-attrs"
    else:
        parser_version = "generic-anchor-list"

    if best_label is None:
        fallback_title = soup.title.string.strip() if soup.title and soup.title.string else "No chapter pattern found"
        best_label = fallback_title

    return {
        "label": best_label,
        "chapter_num": best_num,
        "chapter_url": best_url,
        "confidence": confidence,
        "parser_version": parser_version,
        "candidates": sorted(candidate_debug, key=lambda c: c["score"], reverse=True),
        "error_flags": error_flags,
    }


def pick_best_candidate(soup: BeautifulSoup, page_url: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    info = pick_best_candidate_with_debug(soup, page_url)
    return info["label"], info["chapter_num"], info["chapter_url"]


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


def scrape_bs4(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
    try:
        res = SESSION.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        res.raise_for_status()
    except Exception as exc:
        return None, None, None, f"Request failed: {exc}", {}

    soup = BeautifulSoup(res.text, "html.parser")
    profile = get_profile_for_url(url)
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
    return info.get("label"), info.get("chapter_num"), info.get("chapter_url"), None, info


def scrape_selenium(url: str) -> tuple[Optional[str], Optional[float], Optional[str], Optional[str], dict]:
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
    label, num, latest_url, err, info = scrape_bs4(url)
    if err is None:
        return label, num, latest_url, None, info

    if os.getenv("USE_SELENIUM_FALLBACK", "1") == "1":
        s_label, s_num, s_latest_url, s_err, s_info = scrape_selenium(url)
        if s_err is None:
            return s_label, s_num, s_latest_url, None, s_info
        return None, None, None, f"{err}; {s_err}", {}

    return None, None, None, err, {}


def check_single(bookmark_id: int, user_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id)).fetchone()
        if not row:
            return

        effective_url = resolve_series_listing_url(row["url"])
        label, num, latest_url, err, debug_info = scrape_latest_update(effective_url)
        cover_url = row["cover_url"]
        if not cover_url:
            scraped_cover = scrape_series_cover(effective_url, row["title"] or "")
            cover_url = scraped_cover or row["cover_url"]
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


def check_all(user_id: int) -> None:
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM bookmarks WHERE user_id = ?", (user_id,)).fetchall()
    ids = [row["id"] for row in rows]
    if not ids:
        return
    # Parallel checks significantly reduce total refresh latency.
    with ThreadPoolExecutor(max_workers=min(MAX_CHECK_WORKERS, len(ids))) as pool:
        futures = [pool.submit(check_single, bid, user_id) for bid in ids]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                # Keep the batch moving even if one site fails.
                pass


def check_all_users() -> None:
    with get_conn() as conn:
        users = conn.execute("SELECT id FROM users").fetchall()
    for user in users:
        check_all(int(user["id"]))


@app.route("/auth", methods=["GET", "POST"])
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
                        session["user_id"] = new_user_id
                        conn.execute(
                            "INSERT OR IGNORE INTO bookmarks (user_id, title, url) VALUES (?, ?, ?)",
                            (new_user_id, "Solo Leveling", "https://asurascans.com/comics/solo-leveling-ragnarok-560315bb"),
                        )
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
    with get_conn() as conn:
        rows = conn.execute(
            """
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
            ORDER BY b.id DESC
            """
        , (user_id, user_id, user_id)).fetchall()
    bookmarks = []
    total_unread = 0.0
    behind_count = 0
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
        if unread > 0:
            total_unread += unread
            behind_count += 1
        item["unread_count"] = unread
        item["continue_url"] = (
            item.get("latest_seen_url")
            if unread > 0 and item.get("latest_seen_url")
            else item.get("read_source_url") or item.get("url")
        )
        bookmarks.append(item)
    return render_template(
        "index.html",
        bookmarks=bookmarks,
        current_user=current_user,
        total_unread=int(total_unread) if total_unread.is_integer() else round(total_unread, 1),
        behind_count=behind_count,
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
        headers={"Content-Disposition": 'attachment; filename="manga-tracker-backup.json"'},
    )


@app.route("/import", methods=["POST"])
def import_data():
    if not login_required():
        return redirect(url_for("auth_page"))
    file = request.files.get("backup_file")
    if file is None:
        return redirect(url_for("index"))
    try:
        payload = json.loads(file.read().decode("utf-8"))
    except Exception:
        return redirect(url_for("index"))
    bookmarks = payload.get("bookmarks") or []
    progress = payload.get("reading_progress") or []
    user_id = get_actor_user_id()
    id_map: dict[int, int] = {}
    with get_conn() as conn:
        for b in bookmarks:
            old_id = int(b.get("id") or 0)
            conn.execute(
                """
                INSERT OR IGNORE INTO bookmarks
                (user_id, title, url, latest_seen, latest_seen_num, latest_seen_url, cover_url, new_update, last_checked, last_error, series_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    b.get("title"),
                    b.get("url"),
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
            new_row = conn.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, b.get("url")),
            ).fetchone()
            if old_id and new_row:
                id_map[old_id] = int(new_row["id"])
        for p in progress:
            mapped_bookmark_id = id_map.get(int(p.get("bookmark_id") or 0))
            if mapped_bookmark_id is None:
                continue
            conn.execute(
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
    return redirect(url_for("index"))


@app.route("/add", methods=["POST"])
def add_bookmark():
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    if not title or not url:
        return redirect(url_for("index"))

    cover_url = scrape_series_cover(url, title)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO bookmarks (user_id, title, url, cover_url) VALUES (?, ?, ?, ?)",
            (user_id, title, url, cover_url),
        )
    return redirect(url_for("index"))


@app.route("/check/<int:bookmark_id>", methods=["POST"])
def check_bookmark(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    check_single(bookmark_id, get_actor_user_id())
    return redirect(url_for("index"))


@app.route("/check-all", methods=["POST"])
def check_all_route():
    if not login_required():
        return redirect(url_for("auth_page"))
    check_all(get_actor_user_id())
    return redirect(url_for("index"))


@app.route("/mark-seen/<int:bookmark_id>", methods=["POST"])
def mark_seen(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("UPDATE bookmarks SET new_update = 0 WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect(url_for("index"))


@app.route("/delete/<int:bookmark_id>", methods=["POST"])
def delete_bookmark(bookmark_id: int):
    if not login_required():
        return redirect(url_for("auth_page"))
    user_id = get_actor_user_id()
    with get_conn() as conn:
        conn.execute("DELETE FROM bookmarks WHERE id = ? AND user_id = ?", (bookmark_id, user_id))
    return redirect(url_for("index"))


@app.route("/api/series/ensure", methods=["POST"])
def ensure_series():
    if not api_auth_required():
        return jsonify({"ok": False, "error": "authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    url = (payload.get("url") or "").strip()
    series_key = (payload.get("series_key") or "").strip().lower()
    if not title or not url:
        return jsonify({"ok": False, "error": "title and url required"}), 400

    user_id = get_actor_user_id()
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


@app.route("/api/progress", methods=["POST"])
def save_progress():
    if not api_auth_required():
        return jsonify({"ok": False, "error": "authentication required"}), 401
    payload = request.get_json(silent=True) or {}
    series_url = (payload.get("series_url") or "").strip()
    series_key = (payload.get("series_key") or "").strip().lower()
    chapter_url = (payload.get("chapter_url") or "").strip()
    chapter_label = (payload.get("chapter_label") or "").strip()
    chapter_num = payload.get("chapter_num")

    if not series_url and not series_key:
        return jsonify({"ok": False, "error": "series_url or series_key required"}), 400

    user_id = get_actor_user_id()
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


@app.route("/api/debug/scrape", methods=["POST"])
def debug_scrape():
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


@app.route("/api/maintenance/merge-duplicates", methods=["POST"])
def merge_duplicates():
    if not api_auth_required():
        return jsonify({"ok": False, "error": "authentication required"}), 401
    user_id = get_actor_user_id()
    merged_groups = 0
    deleted_bookmarks = 0

    with get_conn() as conn:
        groups = conn.execute(
            """
            SELECT series_key, GROUP_CONCAT(id) AS ids
            FROM bookmarks
            WHERE user_id = ? AND series_key IS NOT NULL AND TRIM(series_key) <> ''
            GROUP BY series_key
            HAVING COUNT(*) > 1
            """
        , (user_id,)).fetchall()

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
    scheduler.start()
    # Run once at startup so users don't wait for the first interval.
    check_all_users()
    return scheduler


if __name__ == "__main__":
    init_db()
    if not APP_DEBUG or os.getenv("WERKZEUG_RUN_MAIN") == "true":
        setup_scheduler()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=APP_DEBUG)

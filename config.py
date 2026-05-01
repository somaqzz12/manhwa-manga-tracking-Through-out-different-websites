"""Central environment defaults (read once; app + db stay consistent)."""

from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = str(APP_ROOT / "tracker.db")


def _normalize_database_url(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("postgres://"):
        return "postgresql://" + s[len("postgres://") :]
    return s


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL") or "")
IS_POSTGRES = bool(DATABASE_URL)
DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "local@tracker")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
APP_DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
ALLOW_SQLITE_IN_PRODUCTION = os.getenv("ALLOW_SQLITE_IN_PRODUCTION", "0") == "1"

HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
RESOLVE_URL_MAX_LEN = int(os.getenv("RESOLVE_URL_MAX_LEN", "2048"))
RESOLVE_CACHE_TTL_SECONDS = int(os.getenv("RESOLVE_CACHE_TTL_SECONDS", "120"))
DISCOVER_QUERY_MAX_LEN = int(os.getenv("DISCOVER_QUERY_MAX_LEN", "120"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

# Discovery/demo UI and demo APIs are off unless explicitly enabled (simple tracker MVP).
SHOW_DEMO_CONTENT = os.getenv("SHOW_DEMO_CONTENT", "0").strip().lower() in ("1", "true", "yes")

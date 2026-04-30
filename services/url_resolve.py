"""Server-side POST /api/resolve-url handling (cache + adapter resolution)."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import Callable, Optional
from urllib.parse import urlparse

import config
from services import scraping as scraping_services
from services import source_preview
from sources.resolver import normalize_url as default_normalize_url
from sources.resolver import resolve_url as default_resolve_url

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict]] = {}


def _cache_get(key: str, ttl_seconds: int) -> Optional[dict]:
    now = time.time()
    with _LOCK:
        item = _CACHE.get(key)
        if not item:
            return None
        ts, payload = item
        if now - ts > ttl_seconds:
            _CACHE.pop(key, None)
            return None
        return dict(payload)


def _cache_set(key: str, payload: dict) -> None:
    with _LOCK:
        _CACHE[key] = (time.time(), dict(payload))


def resolve_url_post(
    data: dict,
    *,
    is_public_http_url: Optional[Callable[[str], bool]] = None,
    normalize_url_fn: Optional[Callable[[str], str]] = None,
    resolve_url_fn: Optional[Callable[[str], object]] = None,
) -> tuple[dict, int]:
    """
    Validate input, resolve URL through source adapters, return JSON body and HTTP status.
    Mirrors legacy api_resolve_url behavior.

    Optional callables default to scraping/sources implementations; app.py may pass
    attributes so tests can patch app.is_public_http_url / app.source_engine_resolve_url.
    """
    pub = is_public_http_url or scraping_services.is_public_http_url
    norm_fn = normalize_url_fn or default_normalize_url
    res_fn = resolve_url_fn or default_resolve_url

    raw_url = (data.get("url") or "").strip()[: config.RESOLVE_URL_MAX_LEN + 1]
    if not raw_url:
        return {"ok": False, "error": "url is required"}, 400
    if len(raw_url) > config.RESOLVE_URL_MAX_LEN:
        return {"ok": False, "error": "url is too long"}, 400
    raw_parsed = urlparse(raw_url)
    if raw_parsed.scheme and raw_parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "url must use http or https"}, 400
    try:
        normalized = norm_fn(raw_url)
    except Exception:
        return {"ok": False, "error": "invalid url"}, 400
    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "url must use http or https"}, 400
    if not pub(normalized):
        return {"ok": False, "error": "url must be a public http(s) address"}, 400

    cached = _cache_get(normalized, config.RESOLVE_CACHE_TTL_SECONDS)
    if cached is not None:
        return cached, 200

    try:
        preview = res_fn(normalized)
    except Exception:
        fallback = source_preview.coerce_preview_payload(
            {
                "source_url": normalized,
                "support_level": "manual_only",
                "source_name": "Manual",
                "warnings": [
                    "Automatic detection could not read this page from the server. "
                    "You can save it manually, or open it and use the extension to capture metadata from your browser."
                ],
            },
            detection_source="manual",
            fallback_url=normalized,
            is_public_http_url=pub,
        )
        fallback["ok"] = True
        fallback["status"] = "manual"
        fallback["supportLabel"] = source_preview.preview_support_label(fallback.get("support_level"))
        fallback["chaptersFound"] = 0
        _cache_set(normalized, fallback)
        return fallback, 200

    payload = source_preview.coerce_preview_payload(
        asdict(preview), detection_source="backend", fallback_url=normalized, is_public_http_url=pub
    )
    if not payload.get("source_url"):
        payload["source_url"] = normalized
    if not payload.get("source_domain"):
        try:
            payload["source_domain"] = (urlparse(payload["source_url"]).hostname or "").lower().replace("www.", "")
        except Exception:
            payload["source_domain"] = ""
    payload["status"] = "supported" if preview.support_level not in ("manual_only", "blocked") else "manual"
    payload["supportLabel"] = source_preview.preview_support_label(payload.get("support_level"))
    payload["chaptersFound"] = len(payload.get("chapters") or [])
    payload["ok"] = True
    if payload.get("support_level") == "manual_only":
        warnings = list(payload.get("warnings") or [])
        warnings.append(
            "Automatic detection could not read this page from the server. "
            "You can save it manually, or open it and use the extension to capture metadata from your browser."
        )
        payload["warnings"] = warnings
    _cache_set(normalized, payload)
    return payload, 200


def clear_resolve_cache_for_tests() -> None:
    """Test helper: drop cached resolve entries."""
    with _LOCK:
        _CACHE.clear()

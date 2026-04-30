from __future__ import annotations

from typing import Optional


def canonical_and_normalized_series_urls(series_url: str, *, resolve_series_listing_url_cb, normalize_bookmark_url_cb) -> tuple[str, str]:
    canonical_series_url = ""
    normalized_series_url = ""
    if series_url:
        canonical_series_url = resolve_series_listing_url_cb(series_url)
        normalized_series_url = normalize_bookmark_url_cb(canonical_series_url)
    return canonical_series_url, normalized_series_url


def find_progress_bookmark_id(
    conn,
    *,
    user_id: int,
    series_key: str,
    canonical_series_url: str,
    normalized_series_url: str,
) -> Optional[int]:
    row = None
    if series_key:
        row = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND series_key = ?",
            (user_id, series_key),
        ).fetchone()
    if row is None and normalized_series_url:
        candidates = [normalized_series_url]
        if canonical_series_url and canonical_series_url not in candidates:
            candidates.append(canonical_series_url)
        for candidate in candidates:
            row = conn.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND url = ?",
                (user_id, candidate),
            ).fetchone()
            if row is not None:
                break
    if not row:
        return None
    return int(row["id"])


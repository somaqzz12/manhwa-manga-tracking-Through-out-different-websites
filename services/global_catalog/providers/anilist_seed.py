from __future__ import annotations

import re
import time
from typing import Any, Optional

import requests

ANILIST_API = "https://graphql.anilist.co"
QUERY = """
query ($page: Int, perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(type: MANGA, sort: POPULARITY_DESC, isAdult: false) {
      id
      title { english romaji userPreferred }
      description
      genres
      format
      status
      siteUrl
      startDate { year }
      averageScore
      coverImage { large }
    }
  }
}
"""

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "MangaWatchlistCatalog/1.0 (metadata seed)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
)

_RATE_SLEEP_SEC = 0.75


def _strip_html(html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", t).strip()


def _map_status(raw: str | None) -> str:
    s = (raw or "").strip().upper()
    if s == "RELEASING":
        return "ongoing"
    if s == "FINISHED":
        return "completed"
    if s == "HIATUS":
        return "hiatus"
    if s == "CANCELLED":
        return "cancelled"
    return "unknown"


def _map_format(raw: str | None) -> str:
    f = (raw or "").strip().upper()
    if f == "NOVEL":
        return "novel"
    return "manga"


def seed_anilist(
    conn: Any,
    *,
    limit: int,
    page_start: int = 1,
    log: Optional[Any] = None,
) -> int:
    from services.global_catalog import repository as gc_repo

    ingested = 0
    page = max(1, int(page_start))
    per_page = min(50, max(1, int(limit)))
    remaining = max(0, int(limit))

    while remaining > 0:
        time.sleep(_RATE_SLEEP_SEC)
        batch = min(per_page, remaining)
        res = SESSION.post(
            ANILIST_API,
            json={"query": QUERY, "variables": {"page": page, "perPage": batch}},
            timeout=45,
        )
        res.raise_for_status()
        body = res.json()
        if body.get("errors"):
            raise RuntimeError(str(body["errors"])[:500])
        media_list = (body.get("data") or {}).get("Page", {}).get("media") or []
        if not media_list:
            break
        for m in media_list:
            tid = m.get("id")
            titles = m.get("title") or {}
            title = (titles.get("english") or titles.get("romaji") or titles.get("userPreferred") or "").strip()
            if not title:
                continue
            desc = _strip_html(m.get("description") or "")[:8000] or None
            genres = m.get("genres") or []
            if not isinstance(genres, list):
                genres = []
            site = (m.get("siteUrl") or "").strip()
            cover = ((m.get("coverImage") or {}) or {}).get("large") or ""
            year = (m.get("startDate") or {}).get("year")
            try:
                y_int = int(year) if year is not None else None
            except (TypeError, ValueError):
                y_int = None
            score = m.get("averageScore")
            try:
                pop = float(score) * 1000.0 if score is not None else 0.0
            except (TypeError, ValueError):
                pop = 0.0
            gc_repo.ingest_provider_record(
                conn,
                title=title,
                canonical_title=title,
                description=desc,
                cover_url=cover or None,
                type_=_map_format(m.get("format")),
                status=_map_status(m.get("status")),
                year=y_int,
                genres=[str(g) for g in genres if g],
                popularity_score=pop,
                aliases=[str(titles.get("romaji") or "").strip()] if titles.get("romaji") else None,
                external=("anilist", str(tid)),
                source_url=site or None,
                source_name="AniList",
                source_domain="anilist.co",
                source_type="api",
                link_status="verified" if site else "pending",
            )
            ingested += 1
            remaining -= 1
            if remaining <= 0:
                break
        page += 1
        if len(media_list) < batch:
            break

    if log:
        log(f"anilist: ingested {ingested} series")
    return ingested

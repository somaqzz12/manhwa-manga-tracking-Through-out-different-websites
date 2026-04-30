from __future__ import annotations

import time
from typing import Any, Optional

import requests

from sources.adapters.mangadex import MANGADEX_API, _cover_url_from_manga

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "MangaWatchlistCatalog/1.0 (metadata seed)",
        "Accept": "application/json",
    }
)

_RATE_SLEEP_SEC = 0.35


def _map_status(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if s == "ongoing":
        return "ongoing"
    if s == "completed":
        return "completed"
    if s == "hiatus":
        return "hiatus"
    if s == "cancelled":
        return "cancelled"
    return "unknown"


def _map_type_from_lang(lang: str | None) -> str:
    l = (lang or "").strip().lower()
    if l == "ko":
        return "manhwa"
    if l in {"zh", "zh-hk"}:
        return "manhua"
    return "manga"


def seed_mangadex(
    conn: Any,
    *,
    limit: int,
    offset_start: int = 0,
    log: Optional[Any] = None,
) -> int:
    from services.global_catalog import repository as gc_repo

    ingested = 0
    offset = max(0, int(offset_start))
    remaining = max(0, int(limit))
    position = 0
    while remaining > 0:
        batch = min(100, remaining)
        time.sleep(_RATE_SLEEP_SEC)
        res = SESSION.get(
            f"{MANGADEX_API}/manga",
            params={
                "limit": batch,
                "offset": offset,
                "includes[]": ["cover_art"],
                "contentRating[]": ["safe", "suggestive"],
                "order[latestUploadedChapter]": "desc",
            },
            timeout=45,
        )
        res.raise_for_status()
        body = res.json()
        items = body.get("data") or []
        included = body.get("included") or []
        if not items:
            break
        for item in items:
            attrs = item.get("attributes") or {}
            title_map = attrs.get("title") or {}
            title = title_map.get("en") or next(iter(title_map.values()), None)
            if not title:
                continue
            mid = str(item.get("id") or "").strip()
            cover = _cover_url_from_manga(item, included) or ""
            desc_map = attrs.get("description") or {}
            desc = desc_map.get("en") or next(iter(desc_map.values()), None)
            year = attrs.get("year")
            try:
                y_int = int(year) if year is not None else None
            except (TypeError, ValueError):
                y_int = None
            alt_titles: list[str] = []
            for a in attrs.get("altTitles") or []:
                if isinstance(a, dict):
                    for _lang, val in a.items():
                        if val and str(val).strip():
                            alt_titles.append(str(val).strip())
            popularity = float(1_000_000 - position)
            url = f"https://mangadex.org/title/{mid}"
            gc_repo.ingest_provider_record(
                conn,
                title=str(title).strip(),
                canonical_title=str(title).strip(),
                description=(str(desc).strip()[:8000] if desc else None),
                cover_url=cover or None,
                type_=_map_type_from_lang(attrs.get("originalLanguage")),
                status=_map_status(attrs.get("status")),
                year=y_int,
                genres=None,
                popularity_score=popularity,
                aliases=alt_titles[:16],
                external=("mangadex", mid),
                source_url=url,
                source_name="MangaDex",
                source_domain="mangadex.org",
                source_type="api",
                link_status="verified",
            )
            ingested += 1
            position += 1
            remaining -= 1
            if remaining <= 0:
                break
        offset += len(items)
        if len(items) < batch:
            break
    if log:
        log(f"mangadex: ingested {ingested} series (offset now {offset})")
    return ingested

from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Any

SHOW_DEMO_CONTENT = os.getenv("SHOW_DEMO_CONTENT", "").strip().lower() in ("1", "true", "yes")


LOCAL_DISCOVERY_CATALOG = [
    {
        "id": 1,
        "slug": "solo-leveling",
        "title": "Solo Leveling",
        "description": "A weak hunter gains a unique leveling system and rises to the top.",
        "cover_url": None,
        "type": "manhwa",
        "status": "completed",
        "latest_chapter": "179",
        "sources": [
            {"source_id": "asura", "source_name": "Asura", "url": "https://asuracomic.net/series/solo-leveling", "latest_chapter": "179", "chapter_count": 179, "support_level": "site_adapter", "health_status": "working"},
            {"source_id": "reaper", "source_name": "Reaper", "url": "https://reaperscans.com/series/solo-leveling", "latest_chapter": "178", "chapter_count": 178, "support_level": "site_adapter", "health_status": "working"},
            {"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/a1b2c3", "latest_chapter": "200", "chapter_count": 200, "support_level": "official_api", "health_status": "working"},
            {"source_id": "manual", "source_name": "Manual/Other", "url": "", "latest_chapter": None, "chapter_count": None, "support_level": "manual", "health_status": "partial"},
        ],
        "watch_count": 1340,
        "open_count": 922,
        "search_count": 1780,
    },
    {"id": 2, "slug": "tower-of-god", "title": "Tower of God", "description": "A boy enters the Tower to find his friend and faces deadly trials.", "cover_url": None, "type": "manhwa", "status": "ongoing", "latest_chapter": "640", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/tower-of-god", "latest_chapter": "640", "chapter_count": 640, "support_level": "official_api", "health_status": "working"}], "watch_count": 1180, "open_count": 810, "search_count": 1200},
    {"id": 3, "slug": "omniscient-reader", "title": "Omniscient Reader", "description": "A novel reader survives in the world of his favorite story.", "cover_url": None, "type": "manhwa", "status": "ongoing", "latest_chapter": "257", "sources": [{"source_id": "asura", "source_name": "Asura", "url": "https://asuracomic.net/series/omniscient-reader", "latest_chapter": "257", "chapter_count": 257, "support_level": "site_adapter", "health_status": "working"}, {"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/omniscient-reader", "latest_chapter": "257", "chapter_count": 257, "support_level": "official_api", "health_status": "working"}], "watch_count": 1120, "open_count": 730, "search_count": 1080},
    {"id": 4, "slug": "the-beginning-after-the-end", "title": "The Beginning After the End", "description": "A king reincarnates into a magical world and starts over.", "cover_url": None, "type": "manhwa", "status": "ongoing", "latest_chapter": "204", "sources": [{"source_id": "asura", "source_name": "Asura", "url": "https://asuracomic.net/series/the-beginning-after-the-end", "latest_chapter": "204", "chapter_count": 204, "support_level": "site_adapter", "health_status": "working"}], "watch_count": 980, "open_count": 700, "search_count": 1022},
    {"id": 5, "slug": "one-piece", "title": "One Piece", "description": "Pirate adventure to find the legendary treasure.", "cover_url": None, "type": "manga", "status": "ongoing", "latest_chapter": "1113", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/one-piece", "latest_chapter": "1113", "chapter_count": 1113, "support_level": "official_api", "health_status": "working"}], "watch_count": 2120, "open_count": 1600, "search_count": 2310},
    {"id": 6, "slug": "jujutsu-kaisen", "title": "Jujutsu Kaisen", "description": "Curses, sorcerers, and a dangerous power struggle.", "cover_url": None, "type": "manga", "status": "completed", "latest_chapter": "271", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/jujutsu-kaisen", "latest_chapter": "271", "chapter_count": 271, "support_level": "official_api", "health_status": "working"}], "watch_count": 1870, "open_count": 1302, "search_count": 1770},
    {"id": 7, "slug": "chainsaw-man", "title": "Chainsaw Man", "description": "A devil hunter fuses with a chainsaw devil and fights monsters.", "cover_url": None, "type": "manga", "status": "ongoing", "latest_chapter": "196", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/chainsaw-man", "latest_chapter": "196", "chapter_count": 196, "support_level": "official_api", "health_status": "working"}], "watch_count": 1660, "open_count": 1160, "search_count": 1688},
    {"id": 8, "slug": "blue-lock", "title": "Blue Lock", "description": "A ruthless football project to create the ultimate striker.", "cover_url": None, "type": "manga", "status": "ongoing", "latest_chapter": "300", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/blue-lock", "latest_chapter": "300", "chapter_count": 300, "support_level": "official_api", "health_status": "working"}], "watch_count": 1422, "open_count": 1004, "search_count": 1490},
    {"id": 9, "slug": "berserk", "title": "Berserk", "description": "Dark fantasy saga of Guts and the Band of the Hawk.", "cover_url": None, "type": "manga", "status": "ongoing", "latest_chapter": "378", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/berserk", "latest_chapter": "378", "chapter_count": 378, "support_level": "official_api", "health_status": "working"}], "watch_count": 1324, "open_count": 911, "search_count": 1210},
    {"id": 10, "slug": "vinland-saga", "title": "Vinland Saga", "description": "A Viking revenge tale that becomes a story about peace.", "cover_url": None, "type": "manga", "status": "ongoing", "latest_chapter": "220", "sources": [{"source_id": "mangadex", "source_name": "MangaDex", "url": "https://mangadex.org/title/vinland-saga", "latest_chapter": "220", "chapter_count": 220, "support_level": "official_api", "health_status": "working"}], "watch_count": 1040, "open_count": 788, "search_count": 980},
    {
        "id": 11,
        "slug": "lookism",
        "title": "Lookism",
        "description": "A bullied student wakes up in a different body and navigates school life.",
        "cover_url": None,
        "type": "manhwa",
        "status": "ongoing",
        "latest_chapter": "498",
        "sources": [],
        "watch_count": 1010,
        "open_count": 720,
        "search_count": 990,
    },
    {
        "id": 12,
        "slug": "eleceed",
        "title": "Eleceed",
        "description": "A kind young man with super speed teams up with a cat-like mentor.",
        "cover_url": None,
        "type": "manhwa",
        "status": "ongoing",
        "latest_chapter": "318",
        "sources": [],
        "watch_count": 960,
        "open_count": 680,
        "search_count": 940,
    },
]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def score_source(source: dict) -> int:
    score = 50
    if source.get("health_status") == "working":
        score += 20
    if source.get("support_level") == "official_api":
        score += 15
    if source.get("support_level") == "site_adapter":
        score += 10
    if source.get("latest_chapter"):
        score += 10
    if source.get("chapter_count"):
        score += min(int(source.get("chapter_count")) // 20, 10)
    if source.get("health_status") == "blocked":
        score -= 40
    if source.get("health_status") == "broken":
        score -= 30
    return score


def source_label(source: dict) -> str:
    if source.get("support_level") == "manual":
        return "Manual"
    if source.get("support_level") == "official_api":
        return "Automatic"
    if source.get("support_level") == "site_adapter":
        return "Supported"
    if source.get("support_level") == "generic_detector":
        return "Experimental"
    return "Supported"


def _decorate_series(series: dict) -> dict:
    s = deepcopy(series)
    sources = s.get("sources") or []
    ranked = sorted(sources, key=score_source, reverse=True)
    s["sources"] = ranked
    s["sources_found"] = len(ranked)
    s["recommended_source"] = ranked[0]["source_name"] if ranked else None
    for src in s["sources"]:
        src["score"] = score_source(src)
        src["label"] = source_label(src)
    return s


def search_local_series(query: str) -> list[dict]:
    q = _norm(query)
    if not q:
        return []
    out = []
    for row in LOCAL_DISCOVERY_CATALOG:
        hay = f"{_norm(row.get('title', ''))} {_norm(row.get('description', ''))}"
        if q in hay:
            out.append(_decorate_series(row))
    return out


def merge_live_results(results: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for item in results:
        key = _norm(item.get("title", ""))
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "id": abs(hash(key)) % 10_000_000,
                "slug": key.replace(" ", "-"),
                "title": item.get("title"),
                "description": item.get("description"),
                "cover_url": item.get("cover_url"),
                "type": "unknown",
                "status": item.get("status") or "unknown",
                "latest_chapter": item.get("latest_chapter"),
                "sources": [],
                "watch_count": 0,
                "open_count": 0,
                "search_count": 0,
            }
        grouped[key]["sources"].append(
            {
                "source_id": item.get("source_id"),
                "source_name": item.get("source_name"),
                "url": item.get("url"),
                "latest_chapter": item.get("latest_chapter"),
                "chapter_count": item.get("chapter_count"),
                "support_level": item.get("support_level", "site_adapter"),
                "health_status": "working",
            }
        )
    return [_decorate_series(v) for v in grouped.values()]


def trending_snapshot() -> dict:
    if SHOW_DEMO_CONTENT:
        ranked = sorted(LOCAL_DISCOVERY_CATALOG, key=lambda x: x.get("watch_count", 0), reverse=True)
        return {
            "trending_now": [r["title"] for r in ranked[:6]],
            "most_watched": [r["title"] for r in ranked[:6]],
            "recently_updated": [f'{r["title"]} (Ch. {r.get("latest_chapter") or "?"})' for r in ranked[:6]],
            "popular_manhwa": [r["title"] for r in ranked if r.get("type") == "manhwa"][:6],
            "popular_manga": [r["title"] for r in ranked if r.get("type") == "manga"][:6],
        }
    try:
        import db as db_core

        db_core.ensure_db_ready()
        with db_core.get_conn() as conn:
            rows = conn.execute(
                """
                SELECT title, type FROM series
                ORDER BY popularity_score DESC, id ASC
                LIMIT 12
                """
            ).fetchall()
        titles = [str(r["title"] or "") for r in rows if r["title"]]
        manhwa = [str(r["title"] or "") for r in rows if str(r["type"] or "").lower() == "manhwa"]
        manga = [str(r["title"] or "") for r in rows if str(r["type"] or "").lower() in ("manga", "novel", "manhua")]
        return {
            "trending_now": titles[:6],
            "most_watched": titles[:6],
            "recently_updated": titles[:6],
            "popular_manhwa": (manhwa or titles)[:6],
            "popular_manga": (manga or titles)[:6],
        }
    except Exception:
        return {
            "trending_now": [],
            "most_watched": [],
            "recently_updated": [],
            "popular_manhwa": [],
            "popular_manga": [],
        }


def _series_api_dict_from_db(conn: Any, row: Any) -> dict:
    """Build discover-style series dict from a `series` table row (sqlite Row / dict)."""
    import json

    from services.global_catalog import repository as gc_repo

    sid = int(row["id"])
    preview = gc_repo.load_public_source_links(conn, sid)
    sources: list[dict] = []
    for i, p in enumerate(preview):
        sources.append(
            {
                "source_id": re.sub(r"[^a-z0-9]+", "-", str(p.get("source_name") or f"src{i}").lower()).strip("-")[:64]
                or f"src{i}",
                "source_name": p.get("source_name"),
                "url": p.get("url"),
                "latest_chapter": p.get("latest_chapter"),
                "chapter_count": p.get("chapter_count"),
                "support_level": p.get("support_level"),
                "health_status": p.get("health_status") or "working",
            }
        )
    if not sources:
        legacy = conn.execute(
            """
            SELECT source_name, source_domain, source_url, support_level, health_status,
                   latest_chapter, chapter_count
            FROM series_source WHERE series_id = ? ORDER BY id ASC
            """,
            (sid,),
        ).fetchall()
        for i, r in enumerate(legacy):
            sources.append(
                {
                    "source_id": f"legacy-{i}",
                    "source_name": r["source_name"] or "",
                    "url": r["source_url"] or "",
                    "latest_chapter": r["latest_chapter"],
                    "chapter_count": r["chapter_count"],
                    "support_level": r["support_level"] or "manual_only",
                    "health_status": r["health_status"] or "unknown",
                }
            )
    genres: list[str] = []
    try:
        raw_g = row["genres_json"]
    except (KeyError, IndexError, TypeError):
        raw_g = None
    try:
        if raw_g:
            parsed = json.loads(raw_g)
            if isinstance(parsed, list):
                genres = [str(x) for x in parsed if x]
    except Exception:
        genres = []

    base = {
        "id": sid,
        "slug": str(row["slug"] or ""),
        "title": str(row["title"] or ""),
        "description": str(row["description"] or ""),
        "cover_url": str(row["cover_url"] or ""),
        "type": str(row["type"] or "manga"),
        "status": str(row["status"] or "unknown"),
        "latest_chapter": None,
        "sources": sources,
        "watch_count": int(row["popularity_score"] or 0) if row["popularity_score"] is not None else 0,
        "open_count": 0,
        "search_count": 0,
        "series_tags": genres,
    }
    return _decorate_series(base)


def get_series_by_id(series_id: int) -> dict | None:
    try:
        import db as db_core

        db_core.ensure_db_ready()
        with db_core.get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, slug, title, description, cover_url, type, status, popularity_score, genres_json
                FROM series WHERE id = ?
                """,
                (int(series_id),),
            ).fetchone()
            if row:
                return _series_api_dict_from_db(conn, row)
    except Exception:
        pass
    if SHOW_DEMO_CONTENT:
        for row in LOCAL_DISCOVERY_CATALOG:
            if int(row.get("id") or 0) == int(series_id):
                return _decorate_series(row)
    return None


def get_series_by_slug(slug: str) -> dict | None:
    s = (slug or "").strip().lower()
    if not s:
        return None
    try:
        import db as db_core

        db_core.ensure_db_ready()
        with db_core.get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, slug, title, description, cover_url, type, status, popularity_score, genres_json
                FROM series WHERE lower(slug) = lower(?)
                """,
                (s,),
            ).fetchone()
            if row:
                return _series_api_dict_from_db(conn, row)
    except Exception:
        pass
    if SHOW_DEMO_CONTENT:
        for row in LOCAL_DISCOVERY_CATALOG:
            if str(row.get("slug") or "").strip().lower() == s:
                return _decorate_series(row)
    return None

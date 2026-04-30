from __future__ import annotations

import os
from typing import Any

from services import discovery

SHOW_DEMO_CONTENT = os.getenv("SHOW_DEMO_CONTENT", "").strip().lower() in ("1", "true", "yes")

_STARTER_SLUGS = [
    "solo-leveling",
    "omniscient-reader",
    "tower-of-god",
    "the-beginning-after-the-end",
    "jujutsu-kaisen",
    "one-piece",
]

_MANHWA_SLUGS = [
    "solo-leveling",
    "tower-of-god",
    "omniscient-reader",
    "the-beginning-after-the-end",
    "lookism",
    "eleceed",
]

_MANGA_SLUGS = [
    "one-piece",
    "jujutsu-kaisen",
    "chainsaw-man",
    "blue-lock",
    "vinland-saga",
    "berserk",
]


def _by_slug() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in discovery.LOCAL_DISCOVERY_CATALOG:
        slug = str(row.get("slug") or "").strip().lower()
        if slug:
            out[slug] = row
    return out


def _type_label(raw_type: str) -> str:
    t = str(raw_type or "").strip().lower()
    if t == "manhwa":
        return "Manhwa"
    if t == "manhua":
        return "Manhua"
    if t == "novel":
        return "Novel"
    return "Manga"


def _card_from_row(row: dict[str, Any], *, is_demo: bool) -> dict[str, Any]:
    slug = str(row.get("slug") or "").strip().lower()
    title = str(row.get("title") or "").strip()
    latest = str(row.get("latest_chapter") or "?").strip()
    sources = row.get("sources") or []
    sources_found = len(sources)
    return {
        "slug": slug,
        "title": title,
        "type_label": _type_label(str(row.get("type") or "")),
        "latest_chapter": latest or "?",
        "sources_found": sources_found,
        "sources_hint": (f"{sources_found} sources" if sources_found > 0 else "Paste a source URL"),
        "cover_url": str(row.get("cover_url") or "").strip(),
        "is_demo": bool(is_demo),
    }


def _card_from_db_row(row: Any) -> dict[str, Any]:
    slug = str(row["slug"] or "").strip().lower()
    title = str(row["title"] or "").strip()
    sc = int(row["sc"] or 0)
    return {
        "slug": slug,
        "title": title,
        "type_label": _type_label(str(row["type"] or "")),
        "latest_chapter": "—",
        "sources_found": sc,
        "sources_hint": (f"{sc} verified sources" if sc > 0 else "Paste a source URL"),
        "cover_url": str(row["cover_url"] or "").strip(),
        "is_demo": False,
    }


def _cards_for_slugs(slugs: list[str], *, is_demo: bool) -> list[dict[str, Any]]:
    by_slug = _by_slug()
    out: list[dict[str, Any]] = []
    for slug in slugs:
        row = by_slug.get(slug)
        if row:
            out.append(_card_from_row(row, is_demo=is_demo))
    return out


def _source_comparison_rows_from_catalog(*, example_slug: str = "solo-leveling") -> list[dict[str, Any]]:
    row = discovery.get_series_by_slug(example_slug)
    if not row:
        return []
    sources = row.get("sources") or []
    out: list[dict[str, Any]] = []
    for src in sources:
        url = str(src.get("url") or "").strip()
        out.append(
            {
                "source": str(src.get("source_name") or "").strip(),
                "support": discovery.source_label(src),
                "notes": str(src.get("health_status") or "").strip() or "—",
                "url": url,
                "latest_chapter": src.get("latest_chapter"),
                "is_demo": True,
            }
        )
    return out


def _build_from_database(source_policy: dict[str, Any] | None) -> dict[str, Any]:
    import db as db_core

    from services.global_catalog import repository as gc_repo

    db_core.ensure_db_ready()
    with db_core.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.slug, s.title, s.type, s.cover_url,
              (SELECT COUNT(*) FROM series_source_link ssl
               WHERE ssl.series_id = s.id AND ssl.link_status = 'verified') AS sc
            FROM series s
            ORDER BY s.popularity_score DESC, s.id ASC
            LIMIT 24
            """
        ).fetchall()
    cards = [_card_from_db_row(r) for r in rows]
    starter = cards[:6]
    manhwa = [c for c in cards if "manhwa" in (c.get("type_label") or "").lower()][:6]
    manga = [c for c in cards if "manga" in (c.get("type_label") or "").lower()][:6]
    if not manhwa:
        manhwa = cards[6:12] if len(cards) > 6 else cards
    if not manga:
        manga = cards[12:18] if len(cards) > 12 else cards

    recent = []
    for c in cards[:6]:
        recent.append(
            {
                "title": c["title"],
                "source": "Catalog",
                "chapter": "—",
                "status": "Catalog",
                "is_demo": False,
            }
        )

    summary = []
    if isinstance(source_policy, dict):
        for key in ("official_public", "adapter_support", "fallback"):
            bucket = source_policy.get(key) or []
            summary.append(
                {
                    "label": key.replace("_", " ").title(),
                    "count": len(bucket) if isinstance(bucket, list) else 0,
                    "is_demo": False,
                }
            )

    comparison_slug = cards[0]["slug"] if cards else ""
    comparison: list[dict[str, Any]] = []
    if comparison_slug:
        with db_core.get_conn() as conn:
            ser = gc_repo.load_series_row(conn, comparison_slug)
            if ser:
                sid = int(ser["id"])
                for link in gc_repo.load_public_source_links(conn, sid):
                    comparison.append(
                        {
                            "source": link.get("source_name") or "",
                            "support": "Automatic" if link.get("support_level") == "official_api" else "Supported",
                            "notes": "—",
                            "url": link.get("url") or "",
                            "latest_chapter": None,
                            "is_demo": False,
                        }
                    )

    return {
        "starter_picks": starter,
        "popular_manhwa": manhwa,
        "popular_manga": manga,
        "recently_updated_examples": recent,
        "source_comparison_example": comparison,
        "source_comparison_slug": comparison_slug,
        "supported_source_summary": summary,
        "is_demo": False,
    }


def build_discovery_home_data(source_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if SHOW_DEMO_CONTENT:
        ranked = sorted(discovery.LOCAL_DISCOVERY_CATALOG, key=lambda x: int(x.get("watch_count") or 0), reverse=True)
        recent = []
        for row in ranked[:6]:
            recent.append(
                {
                    "title": str(row.get("title") or ""),
                    "source": "Catalog example",
                    "chapter": f"Ch. {str(row.get('latest_chapter') or '?')}",
                    "status": "Example",
                    "is_demo": True,
                }
            )

        summary = []
        if isinstance(source_policy, dict):
            for key in ("official_public", "adapter_support", "fallback"):
                bucket = source_policy.get(key) or []
                summary.append(
                    {
                        "label": key.replace("_", " ").title(),
                        "count": len(bucket) if isinstance(bucket, list) else 0,
                        "is_demo": False,
                    }
                )

        comparison = _source_comparison_rows_from_catalog()
        return {
            "starter_picks": _cards_for_slugs(_STARTER_SLUGS, is_demo=True),
            "popular_manhwa": _cards_for_slugs(_MANHWA_SLUGS, is_demo=True),
            "popular_manga": _cards_for_slugs(_MANGA_SLUGS, is_demo=True),
            "recently_updated_examples": recent,
            "source_comparison_example": comparison,
            "source_comparison_slug": "solo-leveling",
            "supported_source_summary": summary,
            "is_demo": True,
        }

    return _build_from_database(source_policy)

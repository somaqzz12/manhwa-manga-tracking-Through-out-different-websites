from __future__ import annotations

from typing import Any

from services import discovery


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
    return "Manhwa" if t == "manhwa" else "Manga"


def _card_from_row(row: dict[str, Any], *, is_demo: bool) -> dict[str, Any]:
    slug = str(row.get("slug") or "").strip().lower()
    title = str(row.get("title") or "").strip()
    latest = str(row.get("latest_chapter") or "?").strip()
    sources = row.get("sources") or []
    return {
        "slug": slug,
        "title": title,
        "type_label": _type_label(str(row.get("type") or "")),
        "latest_chapter": latest or "?",
        "sources_found": len(sources),
        "cover_url": str(row.get("cover_url") or "").strip(),
        "is_demo": bool(is_demo),
    }


def _cards_for_slugs(slugs: list[str], *, is_demo: bool) -> list[dict[str, Any]]:
    by_slug = _by_slug()
    out: list[dict[str, Any]] = []
    for slug in slugs:
        row = by_slug.get(slug)
        if row:
            out.append(_card_from_row(row, is_demo=is_demo))
    return out


def build_discovery_home_data(source_policy: dict[str, Any] | None = None) -> dict[str, Any]:
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

    return {
        "starter_picks": _cards_for_slugs(_STARTER_SLUGS, is_demo=True),
        "popular_manhwa": _cards_for_slugs(_MANHWA_SLUGS, is_demo=True),
        "popular_manga": _cards_for_slugs(_MANGA_SLUGS, is_demo=True),
        "recently_updated_examples": recent,
        "source_comparison_example": [
            {"source": "MangaDex", "support": "Automatic", "notes": "Public metadata and catalog API", "is_demo": True},
            {"source": "WEBTOON", "support": "Manual", "notes": "Official publisher site; track the URL manually", "is_demo": True},
            {"source": "Asura", "support": "Manual", "notes": "Mirror source; automatic checks can be limited", "is_demo": True},
        ],
        "supported_source_summary": summary,
        "is_demo": True,
    }

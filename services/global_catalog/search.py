from __future__ import annotations

from typing import Any
from urllib.parse import quote

from services.global_catalog import repository as gc_repo


def _proxy_cover_url(raw: str) -> str:
    u = (raw or "").strip()
    if not u:
        return ""
    return "/api/image-proxy?url=" + quote(u, safe="")


def _support_label(level: str) -> str:
    lv = (level or "").strip().lower()
    if lv == "official_api":
        return "Automatic"
    if lv == "site_adapter":
        return "Supported"
    if lv == "generic_detector":
        return "Experimental"
    if lv == "extension_assisted":
        return "Extension-assisted"
    if lv in {"unavailable", "blocked"}:
        return "Unavailable"
    if lv == "protected":
        return "Protected"
    return "Manual"


def discover_rows_from_catalog(conn: Any, query: str, *, limit: int = 24) -> list[dict[str, Any]]:
    """Shape compatible with discover.html / metadata_discovery rows."""
    ids = gc_repo.search_series_ids(conn, query, limit=limit)
    out: list[dict[str, Any]] = []
    for sid in ids:
        row = conn.execute(
            """
            SELECT id, slug, title, description, cover_url, type, status, popularity_score
            FROM series WHERE id = ?
            """,
            (sid,),
        ).fetchone()
        if not row:
            continue
        sc = gc_repo.count_verified_links(conn, sid)
        md_url = gc_repo.first_public_mangadex_url(conn, sid)
        cov = str(row["cover_url"] or "").strip()
        low = cov.lower()
        cover_proxy = _proxy_cover_url(cov) if ("mangadex" in low or "uploads.mangadex" in low) else cov
        best = "Catalog"
        src_url = ""
        if md_url:
            best = "MangaDex"
            src_url = md_url
        elif sc:
            r2 = conn.execute(
                """
                SELECT source_url, source_name FROM series_source_link
                WHERE series_id = ? AND link_status = 'verified'
                ORDER BY id ASC LIMIT 1
                """,
                (sid,),
            ).fetchone()
            if r2:
                src_url = str(r2["source_url"] or "").strip()
                best = str(r2["source_name"] or "Source").strip() or best
        out.append(
            {
                "title": str(row["title"] or "").strip(),
                "slug": str(row["slug"] or "").strip(),
                "description": str(row["description"] or "").strip(),
                "cover_url": cover_proxy,
                "type": str(row["type"] or "manga").title(),
                "source_count": max(sc, 1) if (sc or md_url) else 0,
                "sources_found": sc,
                "best_source": best,
                "latest_chapter": None,
                "chapter_count": None,
                "source_url": src_url,
                "support_level": "official_api" if md_url else "manual_only",
                "support_label": _support_label("official_api" if md_url else "manual_only"),
                "is_demo": False,
                "source_name": best,
                "comparison_slug": str(row["slug"] or "").strip(),
            }
        )
    return out

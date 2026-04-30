"""Real metadata for discover/search: aggregated providers (MangaDex-first), URL resolve, add-from-preview payloads."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from services import discovery as local_discovery
from sources.adapters.mangadex import MangaDexAdapter
from sources import resolver as source_resolver

MANGADEX_UUID_SLUG = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$",
    re.IGNORECASE,
)


def is_mangadex_uuid_slug(slug: str) -> bool:
    return bool(MANGADEX_UUID_SLUG.match((slug or "").strip()))


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
    return "Manual"


def _title_key(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split()).strip()


def _norm_listing_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        path = p.path.rstrip("/") or ""
        return f"{p.scheme}://{normalize_host_netloc(p.netloc)}{path}".lower()
    except Exception:
        return u.lower().rstrip("/")


def normalize_host_netloc(netloc: str) -> str:
    h = (netloc or "").strip().lower()
    if ":" in h and not h.startswith("["):
        h = h.rsplit(":", 1)[0]
    for p in ("www.", "www2.", "m.", "mobile."):
        while h.startswith(p):
            h = h[len(p) :]
    return h


def _format_mangadex_row(raw: dict[str, Any]) -> dict[str, Any]:
    mid = str(raw.get("external_id") or "").strip()
    desc = raw.get("description") or ""
    if isinstance(desc, str) and len(desc) > 2000:
        desc = desc[:2000]
    latest = raw.get("latest_chapter")
    latest_s = str(latest).strip() if latest is not None else ""
    sc = 1
    return {
        "title": str(raw.get("title") or "").strip(),
        "slug": mid,
        "description": desc,
        "cover_url": str(raw.get("cover_url") or "").strip(),
        "type": "Manga",
        "source_count": sc,
        "sources_found": sc,
        "best_source": "MangaDex",
        "latest_chapter": latest_s or None,
        "chapter_count": raw.get("chapter_count"),
        "source_url": str(raw.get("url") or "").strip(),
        "support_level": str(raw.get("support_level") or "official_api"),
        "support_label": _support_label(str(raw.get("support_level") or "official_api")),
        "is_demo": False,
        "source_name": "MangaDex",
        "comparison_slug": None,
    }


def _format_adapter_search_row(raw: dict[str, Any]) -> dict[str, Any]:
    title = str(raw.get("title") or "").strip()
    url = str(raw.get("url") or "").strip()
    ext = str(raw.get("external_id") or "").strip()
    slug_base = ext or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:120]
    slug = slug_base or "series"
    support = str(raw.get("support_level") or "site_adapter").strip().lower()
    if support not in ("official_api", "site_adapter", "generic_detector", "manual_only", "extension_assisted"):
        support = "site_adapter"
    source_name = str(raw.get("source_name") or raw.get("source_id") or "Source").strip()
    desc = raw.get("description") or ""
    if isinstance(desc, str) and len(desc) > 2000:
        desc = desc[:2000]
    latest = raw.get("latest_chapter")
    latest_s = str(latest).strip() if latest is not None else ""
    cov = str(raw.get("cover_url") or "").strip()
    chc = raw.get("chapter_count")
    sc = 1
    return {
        "title": title,
        "slug": slug,
        "description": desc,
        "cover_url": cov,
        "type": "Manga",
        "source_count": sc,
        "sources_found": sc,
        "best_source": source_name,
        "latest_chapter": latest_s or None,
        "chapter_count": chc,
        "source_url": url,
        "support_level": support,
        "support_label": _support_label(support),
        "is_demo": False,
        "source_name": source_name,
        "comparison_slug": None,
    }


def _format_local_demo_row(row: dict[str, Any]) -> dict[str, Any]:
    slug = str(row.get("slug") or "").strip().lower()
    sources = row.get("sources") or []
    sc = len(sources)
    return {
        "title": str(row.get("title") or ""),
        "slug": slug,
        "description": str(row.get("description") or ""),
        "cover_url": str(row.get("cover_url") or "").strip(),
        "type": str(row.get("type") or "unknown").title(),
        "source_count": sc,
        "sources_found": sc,
        "best_source": (row.get("recommended_source") or (sources[0].get("source_name") if sources else "") or ""),
        "latest_chapter": str(row.get("latest_chapter") or "") or None,
        "chapter_count": None,
        "source_url": str((sources[0].get("url") if sources else "") or "").strip(),
        "support_level": str((sources[0].get("support_level") if sources else "") or "manual_only"),
        "support_label": _support_label(str((sources[0].get("support_level") if sources else "") or "manual_only")),
        "is_demo": True,
        "source_name": str((sources[0].get("source_name") if sources else "") or "Catalog"),
        "comparison_slug": None,
    }


def _dedupe_discover_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_url: set[str] = set()
    seen_title_provider: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        u = _norm_listing_url(str(row.get("source_url") or ""))
        title_k = _title_key(str(row.get("title") or ""))
        prov = str(row.get("source_name") or row.get("best_source") or "").strip().lower()
        if u and u in seen_url:
            continue
        if title_k and prov and (title_k, prov) in seen_title_provider:
            continue
        if u:
            seen_url.add(u)
        if title_k and prov:
            seen_title_provider.add((title_k, prov))
        out.append(row)
    return out


def search_title(query: str, *, live: bool = False) -> list[dict[str, Any]]:
    """Aggregate title search: MangaDex first, then other registered adapters (e.g. Asura)."""
    _ = live
    q = (query or "").strip()
    if not q:
        return []
    md_raw = MangaDexAdapter().search(q)
    md_fmt = [_format_mangadex_row(r) for r in md_raw]
    other_raw = source_resolver.search_title(q, skip_adapter_ids={"mangadex"})
    other_fmt = [_format_adapter_search_row(r) for r in other_raw]
    return _dedupe_discover_rows(md_fmt + other_fmt)


def discover_search(query: str, *, live: bool = False) -> dict[str, Any]:
    """
    MangaDex-first aggregated search. When not ``live``, falls back to local demo catalog only if no hits.
    ``live`` skips demo fallback (API / multi-adapter results only).
    """
    q = (query or "").strip()
    if not q:
        return {"ok": True, "results": [], "is_demo": False}

    merged = search_title(q, live=live)
    if live:
        return {"ok": True, "results": merged, "is_demo": False}
    if merged:
        return {"ok": True, "results": merged, "is_demo": False}

    local = local_discovery.search_local_series(q)[:8]
    local_fmt = [_format_local_demo_row(r) for r in local]
    is_demo = bool(local_fmt)
    return {"ok": True, "results": local_fmt, "is_demo": is_demo}


def resolve_url_to_metadata(url: str) -> dict[str, Any] | None:
    """Resolve a URL to preview dict + suggested add-from-preview body."""
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        preview = source_resolver.resolve_url(raw)
    except Exception:
        return None
    pv = asdict(preview)
    dom = ""
    try:
        dom = (urlparse(preview.source_url or raw).hostname or "").strip()
    except Exception:
        dom = ""
    body = save_discovered_series(
        {
            "source_url": preview.source_url or raw,
            "title": preview.title or "",
            "canonical_title": preview.canonical_title or preview.title or "",
            "description": preview.description or "",
            "cover_url": preview.cover_url or "",
            "source_name": preview.source_name or "",
            "source_domain": dom,
            "latest_chapter": preview.latest_chapter or "",
            "chapter_count": preview.chapter_count,
            "support_level": preview.support_level,
            "detection_source": "backend",
        }
    )
    return {"preview": pv, "add_from_preview": body, "support_label": _support_label(str(preview.support_level))}


def save_discovered_series(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalized JSON body for POST /api/library/add-from-preview (client or server)."""
    url = (metadata.get("source_url") or metadata.get("url") or "").strip()
    dom = (metadata.get("source_domain") or "").strip()
    if not dom and url:
        try:
            dom = (urlparse(url).hostname or "").strip()
        except Exception:
            dom = ""
    cc = metadata.get("chapter_count")
    try:
        chapter_count = int(cc) if cc not in (None, "") else None
    except (TypeError, ValueError):
        chapter_count = None
    src_name = str(metadata.get("source_name") or "").strip()[:200]
    if not src_name:
        src_name = "Manual"
    return {
        "source_url": url,
        "title": str(metadata.get("title") or "").strip()[:220],
        "canonical_title": str(metadata.get("canonical_title") or "").strip()[:220],
        "description": str(metadata.get("description") or "").strip()[:2000],
        "cover_url": str(metadata.get("cover_url") or "").strip(),
        "source_name": src_name,
        "source_domain": dom[:200] if dom else None,
        "latest_chapter": str(metadata.get("latest_chapter") or "").strip()[:64],
        "chapter_count": chapter_count,
        "support_level": str(metadata.get("support_level") or "official_api").strip().lower()[:64],
        "detection_source": str(metadata.get("detection_source") or "backend").strip().lower()[:32],
    }


def build_series_page_from_mangadex_uuid(manga_id: str) -> dict[str, Any] | None:
    """SSR for GET /series/<uuid> — one MangaDex source row."""
    mid = (manga_id or "").strip()
    if not is_mangadex_uuid_slug(mid):
        return None
    url = f"https://mangadex.org/title/{mid}"
    meta = resolve_url_to_metadata(url)
    if not meta:
        return None
    pv = meta.get("preview") or {}
    cover = (pv.get("cover_url") or "").strip()
    desc = (pv.get("description") or "").strip()
    title = (pv.get("title") or "MangaDex series").strip()
    latest = pv.get("latest_chapter")
    ch_count = pv.get("chapter_count")
    src_row = {
        "source_name": "MangaDex",
        "source_domain": "mangadex.org",
        "url": url,
        "latest_chapter": latest,
        "latest": latest,
        "chapter_count": ch_count,
        "support_level": "official_api",
        "health_status": "working",
    }
    return {
        "slug": mid,
        "title": title,
        "description": desc,
        "cover_url": cover,
        "source_preview": [src_row],
        "recommended_source": "MangaDex",
        "sources_count": 1,
        "missing_catalog_entry": False,
        "from_mangadex": True,
        "primary_add_url": url,
    }

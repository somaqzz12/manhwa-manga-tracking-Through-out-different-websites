"""Normalized library model: Series, SeriesSource, UserLibraryItem (bookmarks remain legacy)."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from urllib.parse import urlparse


class LibraryModelError(ValueError):
    """Invalid metadata for normalized library writes."""


def normalize_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split()).strip()


def slugify_title(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return (s[:120] if s else "series") or "series"


def _slug_hint_from_url(url: str) -> Optional[str]:
    u = (url or "").strip()
    m = re.search(r"mangadex\.org/title/([a-f0-9-]{36})", u, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def normalize_source_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


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
    return "Manual"


_NON_RECOMMENDABLE_HEALTH = frozenset({"blocked", "broken", "unavailable"})

# Lower rank = better. official_api > site_adapter > extension_assisted > generic_detector > manual.
_SUPPORT_LEVEL_RANK: dict[str, int] = {
    "official_api": 0,
    "site_adapter": 1,
    "extension_assisted": 2,
    "generic_detector": 3,
    "manual_only": 4,
    "manual": 4,
}


def public_support_label(support_level: str, health_status: str) -> str:
    """User-facing support column: includes Unavailable when health blocks the source."""
    h = str(health_status or "").strip().lower()
    if h in _NON_RECOMMENDABLE_HEALTH:
        return "Unavailable"
    return _support_label(support_level)


def _source_row_recommendable(row: dict) -> bool:
    h = str(row.get("health_status") or "").strip().lower()
    if h in _NON_RECOMMENDABLE_HEALTH:
        return False
    url = str(row.get("url") or "").strip()
    return url.startswith("http")


def pick_recommended_source_index(preview: list[dict]) -> Optional[int]:
    best_i: Optional[int] = None
    best_rank = 99
    for i, row in enumerate(preview):
        if not _source_row_recommendable(row):
            continue
        lv = str(row.get("support_level") or "").strip().lower()
        rank = _SUPPORT_LEVEL_RANK.get(lv, 50)
        if rank < best_rank:
            best_rank = rank
            best_i = i
    return best_i


def enrich_public_source_rows(preview: list[Any]) -> list[dict[str, Any]]:
    """Copy preview rows, set label (incl. Unavailable) and is_recommended using priority rules."""
    rows: list[dict[str, Any]] = []
    for raw in preview or []:
        if not isinstance(raw, dict):
            continue
        r = dict(raw)
        r["label"] = public_support_label(str(r.get("support_level") or ""), str(r.get("health_status") or ""))
        rows.append(r)
    rec_i = pick_recommended_source_index(rows)
    for i, r in enumerate(rows):
        r["is_recommended"] = bool(rec_i is not None and i == rec_i)
    return rows


def pick_recommended_cta(rows: list[dict]) -> tuple[str, str]:
    """After enrich_public_source_rows, return (source_name, url) for primary Add-to-library CTA."""
    for r in rows:
        if r.get("is_recommended"):
            return str(r.get("source_name") or "").strip(), str(r.get("url") or "").strip()
    return "", ""


def resolve_public_comparison_slug(
    conn: Any,
    *,
    catalog_slug: str = "",
    title: str = "",
) -> Optional[str]:
    """
    If a normalized series exists for this catalog slug or title, return its DB slug for /series/<slug>.
    Otherwise return None (caller keeps catalog slug).
    """
    cs = (catalog_slug or "").strip().lower()[:120]
    if cs:
        hit = conn.execute("SELECT slug FROM series WHERE lower(slug) = lower(?)", (cs,)).fetchone()
        if hit:
            return str(hit["slug"])
    tkey = normalize_title(title)
    if tkey:
        hit = conn.execute(
            "SELECT slug FROM series WHERE norm_title_key = ? ORDER BY id ASC LIMIT 1",
            (tkey,),
        ).fetchone()
        if hit:
            return str(hit["slug"])
    return None


def _default_source_policy(support_level: str) -> str:
    lv = (support_level or "").strip().lower()
    return "trusted" if lv == "official_api" else "standard"


def _safe_cover_url(raw: str | None, url_validator: Callable[[str], bool]) -> Optional[str]:
    c = (raw or "").strip()
    if not c:
        return None
    if not url_validator(c):
        return None
    return c[:2000]


def get_or_create_series(
    conn: Any,
    *,
    title: str,
    canonical_title: Optional[str],
    description: Optional[str],
    cover_url: Optional[str],
    slug_hint: Optional[str],
    norm_key: str,
    now: str,
) -> int:
    slug_base = ((slug_hint or "").strip().lower() or slugify_title(title))[:120] or "series"
    cur = conn.execute(
        "SELECT id, norm_title_key FROM series WHERE lower(slug) = lower(?)",
        (slug_base,),
    )
    row = cur.fetchone()
    if row and str(row["norm_title_key"] or "") == norm_key:
        return int(row["id"])
    if norm_key:
        hit = conn.execute("SELECT id FROM series WHERE norm_title_key = ?", (norm_key,)).fetchone()
        if hit:
            return int(hit["id"])
    for attempt in range(24):
        use_slug = slug_base if attempt == 0 else f"{slug_base[:96]}-x{attempt}"[:120]
        taken = conn.execute("SELECT id FROM series WHERE lower(slug) = lower(?)", (use_slug,)).fetchone()
        if taken:
            continue
        norm_compact = re.sub(r"[^a-z0-9]+", "", norm_key)
        conn.execute(
            """
            INSERT INTO series (slug, norm_title_key, norm_compact, title, canonical_title, description, cover_url, type, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                use_slug,
                norm_key,
                norm_compact,
                title[:500],
                (canonical_title or None)[:500] if canonical_title else None,
                description,
                cover_url,
                "manga",
                "unknown",
                now,
                now,
            ),
        )
        got = conn.execute("SELECT id FROM series WHERE lower(slug) = lower(?)", (use_slug,)).fetchone()
        if not got:
            raise LibraryModelError("series insert failed")
        return int(got["id"])
    raise LibraryModelError("could not allocate series slug")


def insert_series_source_row(
    conn: Any,
    *,
    series_id: int,
    source_url: str,
    normalized_url: str,
    source_name: Optional[str],
    source_domain: Optional[str],
    support_level: str,
    source_policy: str,
    detection_source: str,
    latest_chapter: Optional[str],
    latest_chapter_url: Optional[str],
    chapter_count: Optional[int],
    now: str,
    url_validator: Callable[[str], bool],
) -> int:
    """Insert a new series_source row; caller must ensure normalized_url is unused."""
    ch_url = (latest_chapter_url or "").strip()
    if ch_url and not url_validator(ch_url):
        ch_url = None
    conn.execute(
        """
        INSERT INTO series_source (
            series_id, source_name, source_domain, source_url, normalized_source_url,
            support_level, source_policy, detection_source,
            latest_chapter, latest_chapter_url, chapter_count, health_status, last_checked_at,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            series_id,
            (source_name or None)[:200] if source_name else None,
            (source_domain or None)[:200] if source_domain else None,
            source_url[:2000],
            normalized_url[:2000],
            support_level[:64],
            source_policy[:64],
            detection_source[:32],
            (latest_chapter[:64] if latest_chapter else None),
            (ch_url[:2000] if ch_url else None),
            chapter_count,
            "unknown",
            now,
            now,
        ),
    )
    got = conn.execute(
        "SELECT id FROM series_source WHERE normalized_source_url = ?",
        (normalized_url,),
    ).fetchone()
    if not got:
        raise LibraryModelError("series_source insert failed")
    return int(got["id"])


def get_or_create_user_library_item(
    conn: Any,
    *,
    user_id: int,
    series_id: int,
    preferred_source_id: int,
    now: str,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id FROM user_library_item WHERE user_id = ? AND series_id = ?",
        (user_id, series_id),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE user_library_item
            SET preferred_source_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (preferred_source_id, now, int(row["id"])),
        )
        return int(row["id"]), False
    conn.execute(
        """
        INSERT INTO user_library_item (user_id, series_id, preferred_source_id, status, notifications_enabled, created_at, updated_at)
        VALUES (?, ?, ?, 'active', 0, ?, ?)
        """,
        (user_id, series_id, preferred_source_id, now, now),
    )
    got = conn.execute(
        "SELECT id FROM user_library_item WHERE user_id = ? AND series_id = ?",
        (user_id, series_id),
    ).fetchone()
    if not got:
        raise LibraryModelError("user_library_item insert failed")
    return int(got["id"]), True


def add_preview_to_library(
    conn: Any,
    user_id: int,
    metadata: dict[str, Any],
    *,
    now: str,
    url_validator: Callable[[str], bool],
) -> dict[str, Any]:
    """
    Idempotent normalized add from preview-shaped metadata.
    Dedupes SeriesSource by normalized_source_url (global).
    """
    source_url = (metadata.get("source_url") or "").strip()
    if not source_url or not url_validator(source_url):
        raise LibraryModelError("valid public source_url is required")
    normalized_url = normalize_source_url(source_url)
    title = (metadata.get("title") or "").strip()
    if not title:
        raise LibraryModelError("title is required")
    canonical_title = (metadata.get("canonical_title") or "").strip() or None
    description = (metadata.get("description") or "").strip() or None
    if description and len(description) > 10000:
        description = description[:10000]
    cover_raw = metadata.get("cover_url")
    cover_url = _safe_cover_url(str(cover_raw) if cover_raw is not None else None, url_validator)
    source_name = (metadata.get("source_name") or "").strip() or None
    source_domain = (metadata.get("source_domain") or "").strip() or None
    if not source_domain:
        try:
            source_domain = (urlparse(source_url).hostname or "").strip()[:200] or None
        except Exception:
            source_domain = None
    support_level = str(metadata.get("support_level") or "manual_only").strip().lower()[:64]
    detection_source = str(metadata.get("detection_source") or "manual").strip().lower()[:32]
    source_policy = str(metadata.get("source_policy") or _default_source_policy(support_level)).strip()[:64]
    latest_chapter = (metadata.get("latest_chapter") or "").strip() or None
    if latest_chapter:
        latest_chapter = latest_chapter[:64]
    latest_chapter_url = (metadata.get("latest_chapter_url") or "").strip() or None
    cc_raw = metadata.get("chapter_count")
    try:
        chapter_count = int(cc_raw) if cc_raw not in (None, "") else None
    except (TypeError, ValueError):
        chapter_count = None
    if chapter_count is not None and chapter_count < 0:
        chapter_count = None

    slug_hint = (metadata.get("slug") or metadata.get("slug_hint") or "").strip() or _slug_hint_from_url(source_url)
    norm_key = normalize_title(title)

    existing = conn.execute(
        "SELECT id, series_id FROM series_source WHERE normalized_source_url = ?",
        (normalized_url,),
    ).fetchone()
    if existing:
        source_id = int(existing["id"])
        series_id = int(existing["series_id"])
        duplicate_source = True
    else:
        series_id = get_or_create_series(
            conn,
            title=title[:500],
            canonical_title=canonical_title,
            description=description,
            cover_url=cover_url,
            slug_hint=slug_hint,
            norm_key=norm_key,
            now=now,
        )
        source_id = insert_series_source_row(
            conn,
            series_id=series_id,
            source_url=source_url,
            normalized_url=normalized_url,
            source_name=source_name,
            source_domain=source_domain,
            support_level=support_level,
            source_policy=source_policy,
            detection_source=detection_source,
            latest_chapter=latest_chapter,
            latest_chapter_url=latest_chapter_url,
            chapter_count=chapter_count,
            now=now,
            url_validator=url_validator,
        )
        duplicate_source = False
    uli_id, uli_new = get_or_create_user_library_item(
        conn, user_id=user_id, series_id=series_id, preferred_source_id=source_id, now=now
    )
    return {
        "series_id": series_id,
        "series_source_id": source_id,
        "user_library_item_id": uli_id,
        "duplicate_source": duplicate_source,
        "user_library_item_created": uli_new,
    }


def load_series_for_public_page(conn: Any, slug: str) -> Optional[dict[str, Any]]:
    """Template kwargs for /series/<slug> when a normalized series exists."""
    from services.global_catalog import repository as gc_repo

    s = (slug or "").strip()[:120]
    if not s:
        return None
    series = conn.execute("SELECT * FROM series WHERE lower(slug) = lower(?)", (s,)).fetchone()
    if not series:
        return None
    sid = int(series["id"])
    preview = gc_repo.load_public_source_links(conn, sid)
    if not preview:
        sources = conn.execute(
            "SELECT * FROM series_source WHERE series_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        for r in sources:
            preview.append(
                {
                    "source_name": r["source_name"] or "",
                    "source_domain": (r["source_domain"] or "").strip(),
                    "url": r["source_url"] or "",
                    "latest_chapter": r["latest_chapter"],
                    "latest": r["latest_chapter"],
                    "chapter_count": r["chapter_count"],
                    "support_level": r["support_level"] or "",
                    "health_status": r["health_status"] or "unknown",
                }
            )
    genres: list[str] = []
    raw_g = series["genres_json"] if "genres_json" in series else None
    if raw_g:
        try:
            import json

            parsed = json.loads(raw_g)
            if isinstance(parsed, list):
                genres = [str(x) for x in parsed if x]
        except Exception:
            genres = []
    return {
        "slug": str(series["slug"]),
        "title": str(series["title"] or ""),
        "description": str(series["description"] or ""),
        "cover_url": str(series["cover_url"] or ""),
        "series_tags": genres,
        "source_preview": preview,
        "recommended_source": "",
        "sources_count": len([p for p in preview if (p.get("url") or "").strip()]),
        "missing_catalog_entry": False,
        "primary_add_url": "",
        "from_mangadex": False,
        "from_normalized": True,
    }


def _support_level_for_extension_profile(profile: Optional[dict]) -> str:
    if not profile:
        return "extension_assisted"
    strat = str(profile.get("parsing_strategy") or "").strip().lower()
    if strat == "mangadex_api":
        return "official_api"
    st = str(profile.get("status") or "").strip().lower()
    if st == "working":
        return "site_adapter"
    return "extension_assisted"


def sync_extension_series_source_for_user(
    conn: Any,
    *,
    user_id: int,
    series_id: int,
    title: str,
    source_url: str,
    source_name: str,
    source_domain: str,
    profile: Optional[dict],
    now: str,
    url_validator: Callable[[str], bool],
) -> Optional[tuple[int, int]]:
    """Create or update ``series_source`` + ``user_library_item`` for an extension listing URL."""
    source_url = (source_url or "").strip()
    if not source_url or not url_validator(source_url):
        raise LibraryModelError("valid source_url is required")
    normalized_url = normalize_source_url(source_url)
    support_level = _support_level_for_extension_profile(profile)
    source_policy = _default_source_policy(support_level)
    row = conn.execute(
        "SELECT id, series_id FROM series_source WHERE normalized_source_url = ?",
        (normalized_url,),
    ).fetchone()
    if row:
        sid_existing = int(row["series_id"])
        source_id = int(row["id"])
        if sid_existing != int(series_id):
            return None
        conn.execute(
            """
            UPDATE series_source SET
                source_name = COALESCE(?, source_name),
                source_domain = COALESCE(?, source_domain),
                detection_source = 'extension',
                updated_at = ?
            WHERE id = ?
            """,
            (
                (source_name or None)[:200] if source_name else None,
                (source_domain or None)[:200] if source_domain else None,
                now,
                source_id,
            ),
        )
    else:
        source_id = insert_series_source_row(
            conn,
            series_id=series_id,
            source_url=source_url,
            normalized_url=normalized_url,
            source_name=source_name,
            source_domain=source_domain,
            support_level=support_level,
            source_policy=source_policy,
            detection_source="extension",
            latest_chapter=None,
            latest_chapter_url=None,
            chapter_count=None,
            now=now,
            url_validator=url_validator,
        )
    uli_id, _ = get_or_create_user_library_item(
        conn, user_id=user_id, series_id=series_id, preferred_source_id=source_id, now=now
    )
    return source_id, uli_id


def touch_user_library_progress_for_bookmark_url(
    conn: Any,
    *,
    user_id: int,
    bookmark_url: str,
    chapter_label: str,
    chapter_num: Optional[float],
    synced_at: str,
) -> None:
    from services.bookmarks import normalize_bookmark_url as _norm_bm

    raw = (bookmark_url or "").strip()
    if not raw:
        return
    nu = normalize_source_url(_norm_bm(raw))
    row = conn.execute(
        """
        SELECT uli.id FROM user_library_item uli
        INNER JOIN series_source ss ON ss.id = uli.preferred_source_id
        WHERE uli.user_id = ? AND ss.normalized_source_url = ?
        """,
        (user_id, nu),
    ).fetchone()
    if not row:
        return
    label = (chapter_label or "").strip()
    if not label and chapter_num is not None:
        label = str(chapter_num)
    conn.execute(
        """
        UPDATE user_library_item
        SET last_read_chapter = ?, last_synced_at = ?, updated_at = ?
        WHERE id = ?
        """,
        ((label[:500] if label else None), synced_at, synced_at, int(row["id"])),
    )

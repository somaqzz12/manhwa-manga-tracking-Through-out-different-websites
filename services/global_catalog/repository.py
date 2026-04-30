from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from services.bookmarks import normalize_bookmark_url
from services.global_catalog.merge import merge_series
from services.global_catalog.normalize import compact_key, search_needles
from services.library_model import normalize_title, slugify_title

NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_url(u: str) -> str:
    return normalize_bookmark_url((u or "").strip())


def find_series_by_external(conn: Any, provider: str, external_id: str) -> Optional[int]:
    row = conn.execute(
        "SELECT series_id FROM series_external_id WHERE provider = ? AND external_id = ?",
        (provider, str(external_id).strip()),
    ).fetchone()
    return int(row["series_id"]) if row else None


def find_series_by_norm_key(conn: Any, norm_key: str) -> Optional[int]:
    row = conn.execute(
        "SELECT id FROM series WHERE norm_title_key = ? ORDER BY id ASC LIMIT 1",
        (norm_key,),
    ).fetchone()
    return int(row["id"]) if row else None


def find_series_by_compact(conn: Any, compact: str) -> Optional[int]:
    if not compact:
        return None
    row = conn.execute(
        "SELECT id FROM series WHERE norm_compact = ? ORDER BY id ASC LIMIT 1",
        (compact,),
    ).fetchone()
    return int(row["id"]) if row else None


def resolve_series_for_ingest(
    conn: Any,
    *,
    norm_key: str,
    compact: str,
    display_title: str = "",
    external: Optional[tuple[str, str]] = None,
) -> tuple[int, bool]:
    """
    Find or allocate series_id for ingest. Returns (series_id, created).
    If external id exists on another series than norm match, merge.
    """
    created = False
    sid_ext: Optional[int] = None
    if external:
        sid_ext = find_series_by_external(conn, external[0], external[1])
    sid_norm = find_series_by_norm_key(conn, norm_key)
    if not sid_norm and compact:
        sid_norm = find_series_by_compact(conn, compact)

    if sid_ext and sid_norm and sid_ext != sid_norm:
        keep, drop = (sid_ext, sid_norm) if sid_ext < sid_norm else (sid_norm, sid_ext)
        merge_series(conn, keep, drop)
        return keep, False
    if sid_ext:
        return sid_ext, False
    if sid_norm:
        return sid_norm, False

    slug = slugify_title(norm_key)[:120] or "series"
    now = NOW()
    for attempt in range(24):
        use_slug = slug if attempt == 0 else f"{slug[:96]}-x{attempt}"[:120]
        taken = conn.execute("SELECT id FROM series WHERE lower(slug) = lower(?)", (use_slug,)).fetchone()
        if taken:
            continue
        title_guess = (display_title or "").strip() or (norm_key.title() if norm_key else "Series")
        conn.execute(
            """
            INSERT INTO series (
                slug, norm_title_key, norm_compact, title, canonical_title, description, cover_url,
                type, status, year, genres_json, popularity_score, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, NULL, NULL, 'manga', 'unknown', NULL, NULL, 0, ?, ?)
            """,
            (use_slug, norm_key, compact, title_guess[:500], now, now),
        )
        got = conn.execute("SELECT id FROM series WHERE lower(slug) = lower(?)", (use_slug,)).fetchone()
        if not got:
            raise RuntimeError("series insert failed")
        return int(got["id"]), True
    raise RuntimeError("could not allocate series slug")


def upsert_series_metadata(
    conn: Any,
    series_id: int,
    *,
    title: str,
    canonical_title: Optional[str],
    description: Optional[str],
    cover_url: Optional[str],
    type_: str,
    status: str,
    year: Optional[int],
    genres: Optional[list[str]],
    popularity_score: float,
    norm_key: str,
    compact: str,
) -> None:
    now = NOW()
    genres_json = json.dumps(genres or [], ensure_ascii=False) if genres else None
    conn.execute(
        """
        UPDATE series SET
            title = ?,
            canonical_title = COALESCE(?, canonical_title),
            description = COALESCE(?, description),
            cover_url = COALESCE(NULLIF(?, ''), cover_url),
            type = ?,
            status = ?,
            year = COALESCE(?, year),
            genres_json = COALESCE(?, genres_json),
            popularity_score = CASE WHEN ? > popularity_score THEN ? ELSE popularity_score END,
            norm_title_key = ?,
            norm_compact = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            title[:500],
            (canonical_title or None)[:500] if canonical_title else None,
            description,
            (cover_url or "").strip(),
            type_[:64],
            status[:64],
            year,
            genres_json,
            popularity_score,
            popularity_score,
            norm_key,
            compact,
            now,
            series_id,
        ),
    )


def add_alias(conn: Any, series_id: int, display: str, *, now: Optional[str] = None) -> None:
    now = now or NOW()
    disp = (display or "").strip()
    if not disp:
        return
    an = normalize_title(disp)
    if not an:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO series_alias (series_id, alias_normalized, alias_display, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (series_id, an, disp[:500], now),
    )


def record_external_id(conn: Any, series_id: int, provider: str, external_id: str, *, now: Optional[str] = None) -> None:
    now = now or NOW()
    pid = str(external_id).strip()
    if not pid:
        return
    other = find_series_by_external(conn, provider, pid)
    if other and other != series_id:
        keeper = min(series_id, other)
        dropp = max(series_id, other)
        merge_series(conn, keeper, dropp)
        series_id = keeper
    conn.execute(
        """
        INSERT OR IGNORE INTO series_external_id (series_id, provider, external_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (series_id, provider[:64], pid[:128], now),
    )


def upsert_source_link(
    conn: Any,
    series_id: int,
    *,
    source_name: str,
    source_domain: str,
    source_url: str,
    source_type: str,
    link_status: str,
    confidence: Optional[float],
    added_by_user_id: Optional[int],
    now: Optional[str] = None,
) -> None:
    now = now or NOW()
    url = (source_url or "").strip()
    if not url:
        return
    nu = _norm_url(url)
    row = conn.execute(
        "SELECT id, series_id FROM series_source_link WHERE normalized_source_url = ?",
        (nu,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE series_source_link SET
                series_id = ?,
                source_name = ?,
                source_domain = ?,
                source_url = ?,
                source_type = ?,
                link_status = ?,
                confidence_score = COALESCE(?, confidence_score),
                last_seen_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                series_id,
                (source_name or None)[:200],
                (source_domain or None)[:200],
                url[:2000],
                source_type[:32],
                link_status[:32],
                confidence,
                now,
                now,
                row["id"],
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO series_source_link (
            series_id, source_name, source_domain, source_url, normalized_source_url,
            source_type, link_status, confidence_score, added_by_user_id, last_seen_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            series_id,
            (source_name or None)[:200],
            (source_domain or None)[:200],
            url[:2000],
            nu[:2000],
            source_type[:32],
            link_status[:32],
            confidence,
            added_by_user_id,
            now,
            now,
            now,
        ),
    )


def count_verified_links(conn: Any, series_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM series_source_link
        WHERE series_id = ? AND link_status = 'verified'
        """,
        (series_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def first_public_mangadex_url(conn: Any, series_id: int) -> str:
    row = conn.execute(
        """
        SELECT source_url FROM series_source_link
        WHERE series_id = ? AND link_status = 'verified' AND source_type = 'api'
          AND (lower(source_domain) LIKE '%mangadex%' OR lower(source_url) LIKE '%mangadex%')
        ORDER BY id ASC LIMIT 1
        """,
        (series_id,),
    ).fetchone()
    return str(row["source_url"] or "").strip() if row else ""


def ingest_provider_record(
    conn: Any,
    *,
    title: str,
    canonical_title: Optional[str],
    description: Optional[str],
    cover_url: Optional[str],
    type_: str,
    status: str,
    year: Optional[int],
    genres: Optional[list[str]],
    popularity_score: float,
    aliases: Optional[Iterable[str]],
    external: Optional[tuple[str, str]],
    source_url: Optional[str],
    source_name: str,
    source_domain: str,
    source_type: str,
    link_status: str,
) -> int:
    """Upsert series + alias + external id + optional verified API link. Returns series_id."""
    norm_key = normalize_title(title)
    compact = compact_key(title)
    if not norm_key:
        raise ValueError("title required")
    series_id, _ = resolve_series_for_ingest(
        conn, norm_key=norm_key, compact=compact, display_title=title, external=external
    )
    upsert_series_metadata(
        conn,
        series_id,
        title=title,
        canonical_title=canonical_title or title,
        description=description,
        cover_url=cover_url,
        type_=type_,
        status=status,
        year=year,
        genres=genres,
        popularity_score=popularity_score,
        norm_key=norm_key,
        compact=compact,
    )
    if external:
        record_external_id(conn, series_id, external[0], external[1])
    if aliases:
        for a in aliases:
            add_alias(conn, series_id, a)
    add_alias(conn, series_id, title)
    if source_url:
        upsert_source_link(
            conn,
            series_id,
            source_name=source_name,
            source_domain=source_domain,
            source_url=source_url,
            source_type=source_type,
            link_status=link_status,
            confidence=0.95 if link_status == "verified" else 0.5,
            added_by_user_id=None,
        )
    return series_id


def attach_extension_or_user_link(
    conn: Any,
    *,
    user_id: int,
    title: str,
    source_url: str,
    source_name: str = "Extension",
    source_domain: str = "",
) -> int:
    """Match or create series; add private pending source link for extension/user."""
    norm_key = normalize_title(title)
    compact = compact_key(title)
    if not norm_key:
        raise ValueError("title required")
    series_id, _ = resolve_series_for_ingest(
        conn, norm_key=norm_key, compact=compact, display_title=title, external=None
    )
    upsert_source_link(
        conn,
        series_id,
        source_name=source_name,
        source_domain=source_domain or "",
        source_url=source_url,
        source_type="extension",
        link_status="private",
        confidence=0.4,
        added_by_user_id=user_id,
    )
    return series_id


def attach_manual_private_link(
    conn: Any,
    *,
    user_id: Optional[int],
    title: str,
    source_url: str,
    source_domain: str,
) -> int:
    norm_key = normalize_title(title)
    compact = compact_key(title)
    series_id, _ = resolve_series_for_ingest(
        conn, norm_key=norm_key, compact=compact, display_title=title, external=None
    )
    upsert_source_link(
        conn,
        series_id,
        source_name="Manual",
        source_domain=source_domain,
        source_url=source_url,
        source_type="manual",
        link_status="private",
        confidence=0.3,
        added_by_user_id=user_id,
    )
    return series_id


def search_series_ids(conn: Any, query: str, limit: int = 48) -> list[int]:
    n, c = search_needles(query)
    if not n and not c:
        return []
    like_n = f"%{n}%" if n else ""
    like_c = f"%{c}%" if c else ""
    seen: set[int] = set()
    out: list[int] = []

    def add_rows(rows: list[Any]) -> None:
        for r in rows:
            sid = int(r["id"])
            if sid not in seen:
                seen.add(sid)
                out.append(sid)

    if n:
        add_rows(
            conn.execute(
                """
                SELECT id FROM series
                WHERE norm_title_key LIKE ? OR norm_compact LIKE ?
                ORDER BY popularity_score DESC, id ASC
                LIMIT ?
                """,
                (like_n, like_c or like_n, limit * 2),
            ).fetchall()
        )
    if c and len(out) < limit:
        add_rows(
            conn.execute(
                """
                SELECT id FROM series
                WHERE norm_compact LIKE ?
                ORDER BY popularity_score DESC, id ASC
                LIMIT ?
                """,
                (like_c, limit * 2),
            ).fetchall()
        )
    if n and len(out) < limit:
        add_rows(
            conn.execute(
                """
                SELECT DISTINCT s.id AS id
                FROM series s
                INNER JOIN series_alias a ON a.series_id = s.id
                WHERE a.alias_normalized LIKE ?
                ORDER BY s.popularity_score DESC, s.id ASC
                LIMIT ?
                """,
                (like_n, limit * 2),
            ).fetchall()
        )
    return out[:limit]


def load_public_source_links(conn: Any, series_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT source_name, source_domain, source_url, source_type, link_status, confidence_score
        FROM series_source_link
        WHERE series_id = ? AND link_status = 'verified'
        ORDER BY
            CASE source_type WHEN 'api' THEN 0 WHEN 'manual' THEN 1 ELSE 2 END,
            id ASC
        """,
        (series_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "source_name": r["source_name"] or "",
                "source_domain": (r["source_domain"] or "").strip(),
                "url": r["source_url"] or "",
                "support_level": "official_api" if (r["source_type"] or "") == "api" else "site_adapter",
                "health_status": "working",
                "latest_chapter": None,
                "chapter_count": None,
            }
        )
    return out


def load_series_row(conn: Any, slug: str) -> Optional[Any]:
    return conn.execute(
        "SELECT * FROM series WHERE lower(slug) = lower(?)",
        ((slug or "").strip()[:120],),
    ).fetchone()

"""Group bookmarks that share a logical story (multi-source / alternate sites)."""

from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import urlparse


def story_id_from_series_key(series_key: str) -> str:
    sk = (series_key or "").strip().lower()
    h = hashlib.sha256(sk.encode("utf-8")).hexdigest()[:16]
    return f"sk-{h}"


def new_solo_story_id() -> str:
    return f"sg-{secrets.token_hex(8)}"


def effective_story_id(row: dict) -> str:
    sid = (row.get("story_id") or "").strip()
    if sid:
        return sid
    return f"solo-legacy-{row.get('id')}"


def aggregate_story_items(items: list[dict]) -> dict[str, Any]:
    """Merge bookmark rows that share a story into one dashboard card."""
    if not items:
        raise ValueError("empty story group")
    items = sorted(items, key=lambda x: int(x.get("id") or 0))

    def best_num_row(num_key: str) -> Optional[dict]:
        best: Optional[dict] = None
        best_n = None
        for it in items:
            raw = it.get(num_key)
            if raw is None:
                continue
            try:
                n = float(raw)
            except (TypeError, ValueError):
                continue
            if best_n is None or n > best_n:
                best_n = n
                best = it
        return best

    latest_row = best_num_row("latest_seen_num")
    latest_num = float(latest_row["latest_seen_num"]) if latest_row and latest_row.get("latest_seen_num") is not None else None
    latest_url = (latest_row or {}).get("latest_seen_url") if latest_row else None
    latest_lbl = (latest_row or {}).get("latest_seen") if latest_row else None
    listing_with_latest = latest_row or items[-1]

    read_row = best_num_row("read_chapter_num")
    read_num = float(read_row["read_chapter_num"]) if read_row and read_row.get("read_chapter_num") is not None else None
    read_url = (read_row or {}).get("read_source_url") if read_row else None
    read_lbl = (read_row or {}).get("read_chapter_label") if read_row else None

    titles = [(it.get("title") or "").strip() for it in items]
    title = max(titles, key=len) if titles else (items[0].get("title") or "")

    primary = min(items, key=lambda x: int(x.get("id") or 0))
    # When no row has a numeric latest (or merge left gaps), still surface chapter URL/label from primary.
    if latest_row is None:
        if primary.get("latest_seen_num") is not None:
            try:
                latest_num = float(primary["latest_seen_num"])
            except (TypeError, ValueError):
                latest_num = None
        if not (latest_url or "").strip():
            latest_url = primary.get("latest_seen_url")
        if not (latest_lbl or "").strip():
            latest_lbl = primary.get("latest_seen")
    new_update = max(int(it.get("new_update") or 0) for it in items)

    hosts: list[str] = []
    for it in items:
        host = urlparse((it.get("url") or "").strip()).netloc.replace("www.", "")
        if host and host not in hosts:
            hosts.append(host)

    cover_url = next((it.get("cover_url") for it in items if it.get("cover_url")), None)

    unread = 0.0
    if latest_num is not None and read_num is not None:
        unread = max(0.0, float(latest_num) - float(read_num))
    elif latest_num is not None and read_num is None and new_update:
        try:
            unread = max(0.0, float(latest_num))
        except (TypeError, ValueError):
            pass

    last_err = None
    parser_v = None
    for it in sorted(items, key=lambda x: (x.get("last_checked") or ""), reverse=True):
        if it.get("last_error"):
            last_err = it.get("last_error")
            parser_v = it.get("latest_parser_version")
            break

    story_id = (primary.get("story_id") or "").strip() or effective_story_id(primary)

    out: dict[str, Any] = {
        "id": int(primary["id"]),
        "story_id": story_id,
        "title": title,
        "url": primary.get("url") or "",
        "cover_url": cover_url,
        "chapter_count": primary.get("chapter_count"),
        "latest_seen_num": latest_num,
        "latest_seen_url": latest_url,
        "latest_seen": latest_lbl,
        "read_chapter_num": read_num,
        "read_source_url": read_url,
        "read_chapter_label": read_lbl,
        "unread_count": unread,
        "continue_url": (read_url or "").strip()
        or ((latest_url or "").strip() if latest_url else "")
        or (primary.get("url") or ""),
        "new_update": new_update,
        "source_count": len(items),
        "source_hosts": hosts,
        "source_bookmark_ids": [int(it["id"]) for it in items],
        "last_error": last_err,
        "latest_parser_version": parser_v,
        "genre": primary.get("genre") or "",
        "series_key": primary.get("series_key"),
    }
    if any(str(it.get("detection_source") or "").lower() == "extension" for it in items):
        out["detection_source"] = "extension"
    sync_vals = [str(it.get("last_synced_at") or "").strip() for it in items if (it.get("last_synced_at") or "").strip()]
    if sync_vals:
        out["last_synced_at"] = max(sync_vals)
    sdom = (primary.get("source_domain") or "").strip()
    if sdom:
        out["source_domain"] = sdom
    for k in (
        "_support_label",
        "_chapter_count_display",
        "_source_display_name",
        "_source_display_domain",
    ):
        v = primary.get(k)
        if v is not None and v != "":
            out[k] = v
    if "has_bookmark" in primary:
        out["has_bookmark"] = bool(primary["has_bookmark"])
    return out


def group_and_aggregate(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        d = dict(r)
        sid = effective_story_id(d)
        by[sid].append(d)
    return [aggregate_story_items(g) for g in by.values()]


def sort_story_cards(cards: list[dict], sort: str) -> list[dict]:
    if sort == "title":
        return sorted(cards, key=lambda c: (c.get("title") or "").lower())
    if sort == "updated":
        return sorted(cards, key=lambda c: (c.get("_last_checked") or ""), reverse=True)
    if sort == "unread":
        return sorted(cards, key=lambda c: float(c.get("unread_count") or 0.0), reverse=True)
    return sorted(cards, key=lambda c: int(c.get("_added_id") or c.get("id") or 0), reverse=True)


def attach_sort_keys(cards: list[dict], raw_by_id: dict[int, dict]) -> None:
    """Fill _added_id and _last_checked from any source row in the story."""
    for c in cards:
        ids = c.get("source_bookmark_ids") or [c["id"]]
        c["_added_id"] = min(ids)
        checked: list[str] = []
        for i in ids:
            row = raw_by_id.get(i)
            if row and row.get("last_checked"):
                checked.append(str(row["last_checked"]))
        c["_last_checked"] = max(checked) if checked else ""

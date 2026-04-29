"""Lightweight, heuristic 'smart' hints from reading patterns (no ML)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_MURIM = re.compile(r"murim|martial|demonic|heavenly|murim|jianghu|wuxia|xianxia", re.I)
_REGRESSION = re.compile(r"regress|returner|reborn|time.?travel|second life|again", re.I)
_ROMCOM = re.compile(r"romance|villainess|duke|princess|office|dating", re.I)
_ACTION = re.compile(r"solo|leveling|hunter|dungeon|tower|apocalypse", re.I)


def _bucket(title: str) -> str | None:
    t = title or ""
    if _MURIM.search(t):
        return "murim / martial fantasy"
    if _REGRESSION.search(t):
        return "regression / second chance"
    if _ROMCOM.search(t):
        return "romance / drama"
    if _ACTION.search(t):
        return "action / leveling"
    return None


def build_insights(story_cards: list[dict]) -> dict[str, Any]:
    """Return suggestion strings for the dashboard (deterministic heuristics)."""
    if not story_cards:
        return {"hints": [], "binge_wait": False}

    buckets: dict[str, int] = {}
    dropped_murim = 0
    murim_started = 0
    backlog_ge_5 = 0

    for c in story_cards:
        title = str(c.get("title") or "")
        b = _bucket(title)
        if b:
            buckets[b] = buckets.get(b, 0) + 1
        if _MURIM.search(title):
            murim_started += 1
            unread = float(c.get("unread_count") or 0)
            latest = c.get("latest_seen_num")
            read = c.get("read_chapter_num")
            if latest is not None and read is not None:
                try:
                    if float(latest) - float(read) <= 0.5:
                        dropped_murim += 1
                except (TypeError, ValueError):
                    pass
        if float(c.get("unread_count") or 0) >= 5.0:
            backlog_ge_5 += 1

    hints: list[str] = []

    if buckets:
        top = max(buckets.items(), key=lambda x: x[1])
        if top[1] >= 2:
            hints.append(
                f"You often read “{top[0]}” — here is something similar to try from your backlog, "
                "or pick a different vibe to avoid fatigue."
            )

    if murim_started >= 3 and dropped_murim >= 3:
        hints.append(
            "You dropped several murim / martial series while barely ahead — if that was intentional, "
            "consider removing them so the dashboard matches what you still want to finish."
        )

    binge_wait = backlog_ge_5 >= 2
    if binge_wait:
        hints.append(
            "You usually binge when 5+ chapters pile up on multiple series — waiting before starting "
            "another title can make catch-up sessions feel better (and saves checks)."
        )

    return {"hints": hints, "binge_wait": binge_wait, "top_bucket": max(buckets, key=buckets.get) if buckets else None}


def rank_next_up(story_cards: list[dict], insights: dict[str, Any] | None = None) -> list[dict]:
    """Order stories for a 'read next' queue (heuristic, deterministic)."""
    insights = insights or {}
    top_bucket = insights.get("top_bucket")
    scored: list[tuple[float, int, dict]] = []
    for c in story_cards:
        unread = float(c.get("unread_count") or 0)
        nu = int(c.get("new_update") or 0)
        score = unread * 8.0 + nu * 50.0
        last_ts = str(c.get("_last_checked") or "").strip()
        if last_ts:
            try:
                dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
            except Exception:
                days = 0.0
        else:
            days = 400.0
        if days > 90:
            score *= 0.35
        if top_bucket:
            b = _bucket(str(c.get("title") or ""))
            if b == top_bucket:
                score += 12.0
        scored.append((score, -int(c.get("_added_id") or c.get("id") or 0), c))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [c for _, __, c in scored]

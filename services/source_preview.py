"""Normalize URL/source preview payloads for the web UI and library APIs."""

from __future__ import annotations

import math
from typing import Callable, Optional

from services import chapter_parsing
from services import scraping as scraping_services

_PREVIEW_SUPPORT_LEVELS = frozenset(
    {
        "official_api",
        "site_adapter",
        "generic_detector",
        "protected",
        "extension_assisted",
        "manual_only",
        "requested",
        "blocked",
    }
)


def preview_support_label(raw: str) -> str:
    level = str(raw or "").strip().lower()
    if level == "official_api":
        return "Automatic"
    if level == "site_adapter":
        return "Supported"
    if level == "generic_detector":
        return "Experimental"
    if level == "protected":
        return "Protected"
    if level in {"extension_assisted", "requested"}:
        return "Requested"
    if level == "blocked":
        return "Unavailable"
    return "Manual"


def preview_latest_chapter_num(raw: str) -> Optional[float]:
    s = str(raw or "").strip()
    if not s:
        return None
    n = chapter_parsing.parse_chapter_number(s)
    if n is not None and math.isfinite(n) and n >= 0:
        return float(n)
    try:
        v = float(s)
        if math.isfinite(v) and v >= 0:
            return v
    except (TypeError, ValueError):
        pass
    return None


def chapter_preview_dict(raw: dict, *, is_public_http_url: Callable[[str], bool]) -> dict:
    item = raw if isinstance(raw, dict) else {}
    url = str(item.get("url") or "").strip()
    if not is_public_http_url(url):
        return {}
    out = {"url": url}
    number = str(item.get("number") or "").strip()
    if number:
        out["number"] = number
    title = str(item.get("title") or "").strip()
    if title:
        out["title"] = title
    released = str(item.get("released_at") or "").strip()
    if released:
        out["released_at"] = released
    return out


def coerce_preview_payload(
    raw: dict,
    *,
    detection_source: str,
    fallback_url: str = "",
    is_public_http_url: Optional[Callable[[str], bool]] = None,
) -> dict:
    pub = is_public_http_url or scraping_services.is_public_http_url
    data = raw if isinstance(raw, dict) else {}
    source_url = str(data.get("source_url") or data.get("url") or fallback_url or "").strip()
    source_name = str(data.get("source_name") or "").strip()
    source_domain = str(data.get("source_domain") or "").strip()
    support_level = str(data.get("support_level") or "manual_only").strip().lower()
    if support_level not in _PREVIEW_SUPPORT_LEVELS:
        support_level = "manual_only"
    title = str(data.get("title") or "").strip()[:220]
    canonical_title = str(data.get("canonical_title") or "").strip()[:220]
    description = str(data.get("description") or "").strip()[:2000]
    cover_url = str(data.get("cover_url") or "").strip()
    if cover_url and not pub(cover_url):
        cover_url = ""
    latest_chapter = str(data.get("latest_chapter") or "").strip()
    latest_chapter_url = str(data.get("latest_chapter_url") or "").strip()
    if latest_chapter_url and not pub(latest_chapter_url):
        latest_chapter_url = ""
    current_chapter = str(data.get("current_chapter") or "").strip()
    chapter_count_raw = data.get("chapter_count")
    try:
        chapter_count = int(chapter_count_raw) if chapter_count_raw not in (None, "") else None
    except (TypeError, ValueError):
        chapter_count = None
    if chapter_count is not None and chapter_count < 0:
        chapter_count = None
    warnings = [str(w).strip() for w in (data.get("warnings") or []) if str(w or "").strip()]
    chapters_raw = data.get("chapters")
    chapters = []
    if isinstance(chapters_raw, list):
        for ch in chapters_raw[:40]:
            row = chapter_preview_dict(ch, is_public_http_url=pub)
            if row:
                chapters.append(row)
    confidence_raw = data.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    capabilities = ["url_resolve", "extension_detect"]
    if support_level == "official_api":
        capabilities.extend(["website_search", "chapter_check", "cover_image"])
    elif support_level in {"site_adapter", "generic_detector"}:
        capabilities.extend(["chapter_check", "cover_image"])
    elif support_level == "protected":
        capabilities = ["manual_only", "extension_detect"]
    elif support_level in {"manual_only", "blocked", "requested"}:
        capabilities = ["manual_only"]
    return {
        "source_url": source_url,
        "source_name": source_name or "Manual",
        "source_domain": source_domain,
        "support_level": support_level,
        "title": title,
        "canonical_title": canonical_title,
        "description": description,
        "cover_url": cover_url,
        "latest_chapter": latest_chapter,
        "latest_chapter_url": latest_chapter_url,
        "current_chapter": current_chapter,
        "chapter_count": chapter_count,
        "chapters": chapters,
        "warnings": warnings,
        "capabilities": capabilities,
        "detection_source": detection_source if detection_source in ("backend", "extension", "manual") else "manual",
        "confidence": confidence,
    }

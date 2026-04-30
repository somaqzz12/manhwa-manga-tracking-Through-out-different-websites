from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from sources.adapters.asura import AsuraAdapter
from sources.adapters.css_source import load_css_adapters_from_profiles
from sources.adapters.mangadex import MangaDexAdapter
from sources.generic_detector import GenericDetector

REGISTRY_JSON_PATH = Path(__file__).resolve().parent / "sources.registry.json"
CSS_ADAPTER_PROFILES_PATH = Path(__file__).resolve().parent / "css_adapter_profiles.json"


def _load_registry_json() -> list[dict]:
    if not REGISTRY_JSON_PATH.exists():
        return []
    try:
        raw = json.loads(REGISTRY_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for row in raw:
        if isinstance(row, dict):
            out.append(row)
    return out


def _legacy_from_sources(row: dict) -> dict:
    support = (row.get("support_level") or row.get("support") or "").strip().lower()
    if support == "official_api":
        tier = "official_public"
        status = "supported"
    elif support == "site_adapter":
        tier = "adapter_support"
        status = "supported"
    elif support == "generic_detector":
        tier = "fallback"
        status = "experimental"
    elif support == "manual_only":
        tier = "premium_manual"
        status = "manual_only"
    elif support == "requested":
        tier = "requested"
        status = "requested"
    elif support == "blocked":
        tier = "blocked"
        status = "blocked"
    else:
        tier = "fallback"
        support = "manual_only"
        status = "manual_only"
    capabilities = _capabilities_from_registry_row(row, support=support, enabled=((row.get("adapter_status") in {"enabled", "enabled_candidate"}) or bool(row.get("enabled"))))
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "domains": row.get("domains") or [],
        "support": support,
        "enabled": (row.get("adapter_status") in {"enabled", "enabled_candidate"}) or bool(row.get("enabled")),
        "adapter": row.get("adapter"),
        "tier": tier,
        "support_level": support,
        "status": status,
        "risk_level": row.get("risk_level"),
        "source_type": row.get("source_type"),
        "homepage": row.get("homepage"),
        "capabilities": capabilities,
    }


def _capabilities_from_registry_row(row: dict, *, support: str, enabled: bool) -> list[str]:
    caps: set[str] = {"url_resolve", "extension_detect"}
    if support == "official_api":
        caps.update({"website_search", "chapter_check", "cover_image"})
    if support in {"site_adapter", "generic_detector"} and enabled:
        caps.update({"chapter_check", "cover_image"})
    if bool(row.get("can_search_titles")) and support == "official_api":
        caps.add("website_search")
    if support == "manual_only":
        caps.add("manual_only")
    if support == "blocked":
        caps.update({"protected", "manual_only"})
    if not enabled and support in {"site_adapter", "generic_detector"}:
        caps.add("stub")
    return sorted(caps)


SOURCE_REGISTRY = [_legacy_from_sources(row) for row in _load_registry_json()]


CSS_SOURCE_ADAPTERS = load_css_adapters_from_profiles(CSS_ADAPTER_PROFILES_PATH)

ADAPTERS = [
    MangaDexAdapter(),
    *CSS_SOURCE_ADAPTERS,
    AsuraAdapter(),
]

GENERIC_DETECTOR = GenericDetector()


def adapter_supports(adapter, capability: str) -> bool:
    cap = str(capability or "").strip().lower()
    if not cap:
        return False
    aid = str(getattr(adapter, "id", "") or "").strip().lower()
    if not aid:
        return False
    for row in SOURCE_REGISTRY:
        if str(row.get("id") or "").strip().lower() != aid:
            continue
        row_caps = {str(c).strip().lower() for c in (row.get("capabilities") or [])}
        if cap in row_caps:
            return True
        if cap == "website_search" and "title_search" in row_caps:
            return True
        if cap == "title_search" and "website_search" in row_caps:
            return True
        return False
    if aid == "mangadex":
        return cap in {"website_search", "title_search", "url_resolve", "chapter_check", "cover_image"}
    return cap == "url_resolve"


def list_sources_by_capability(capability: str) -> list[dict]:
    cap = str(capability or "").strip().lower()
    if not cap:
        return []
    out: list[dict] = []
    for row in SOURCE_REGISTRY:
        caps = {str(c).strip().lower() for c in (row.get("capabilities") or [])}
        if cap in caps:
            out.append(dict(row))
            continue
        if cap == "website_search" and "title_search" in caps:
            out.append(dict(row))
            continue
        if cap == "title_search" and "website_search" in caps:
            out.append(dict(row))
    return out


def get_source_capabilities(source_id_or_url: str) -> list[str]:
    raw = str(source_id_or_url or "").strip()
    if not raw:
        return ["manual_only"]
    if "://" in raw:
        host = (urlparse(raw).netloc or "").lower().replace("www.", "")
        for row in SOURCE_REGISTRY:
            domains = [str(d).strip().lower().replace("www.", "") for d in (row.get("domains") or [])]
            if any(host == d or host.endswith("." + d) for d in domains if d):
                caps = row.get("capabilities")
                if isinstance(caps, list) and caps:
                    return [str(c) for c in caps]
                return ["url_resolve"]
        return ["manual_only"]
    sid = raw.lower()
    for row in SOURCE_REGISTRY:
        if str(row.get("id") or "").strip().lower() == sid:
            caps = row.get("capabilities")
            if isinstance(caps, list) and caps:
                return [str(c) for c in caps]
            return ["url_resolve"]
    return ["manual_only"]


def supported_source_policy() -> dict:
    grouped: dict[str, list[dict]] = {
        "official_public": [],
        "adapter_support": [],
        "fallback": [],
        "premium_manual": [],
        "requested": [],
        "blocked": [],
    }
    for row in SOURCE_REGISTRY:
        grouped.setdefault(row["tier"], []).append(row)
    return grouped

from __future__ import annotations

import json
from pathlib import Path

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
    }


SOURCE_REGISTRY = [_legacy_from_sources(row) for row in _load_registry_json()]


CSS_SOURCE_ADAPTERS = load_css_adapters_from_profiles(CSS_ADAPTER_PROFILES_PATH)

ADAPTERS = [
    MangaDexAdapter(),
    *CSS_SOURCE_ADAPTERS,
    AsuraAdapter(),
]

GENERIC_DETECTOR = GenericDetector()


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

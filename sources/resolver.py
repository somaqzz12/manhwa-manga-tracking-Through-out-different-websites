from __future__ import annotations

from urllib.parse import urlparse

from sources.base import SourcePreview
from sources.registry import ADAPTERS, GENERIC_DETECTOR, adapter_supports, list_sources_by_capability

_HOST_PREFIXES = ("www.", "www2.", "m.", "mobile.")


def normalize_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized
    return normalized


def normalize_host(netloc: str) -> str:
    """Lowercase host without common leading prefixes (www, m, mobile)."""
    h = (netloc or "").strip().lower()
    if not h:
        return ""
    if h.startswith("[") and "]" in h:
        return h
    if ":" in h and not h.startswith("["):
        h = h.rsplit(":", 1)[0]
    changed = True
    while changed:
        changed = False
        for p in _HOST_PREFIXES:
            if h.startswith(p):
                h = h[len(p) :]
                changed = True
    return h


def get_domain(url: str) -> str:
    parsed = urlparse(url)
    return normalize_host(parsed.netloc or "")


def adapter_matches_host(adapter, host_norm: str) -> bool:
    if not host_norm:
        return False
    for d in getattr(adapter, "domains", []) or []:
        dom = str(d).lower().strip()
        if not dom:
            continue
        if host_norm == dom or host_norm.endswith("." + dom):
            return True
    return False


def resolve_url(url: str) -> SourcePreview:
    normalized = normalize_url(url)
    host = get_domain(normalized)
    for adapter in ADAPTERS:
        if adapter_matches_host(adapter, host):
            try:
                return adapter.resolve_url(normalized)
            except Exception:
                continue
    try:
        return GENERIC_DETECTOR.resolve_url(normalized)
    except Exception:
        return SourcePreview(
            source_name="Unknown Site",
            source_url=normalized,
            support_level="manual_only",
            confidence=0.0,
            title="",
            warnings=["Automatic detection failed. Save this URL manually or use the extension."],
        )


def search_title(query: str, *, skip_adapter_ids: set[str] | None = None) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    skip = skip_adapter_ids or set()
    out: list[dict] = []
    for adapter in ADAPTERS:
        aid = str(getattr(adapter, "id", "") or "")
        if aid in skip:
            continue
        if not adapter_supports(adapter, "title_search"):
            continue
        try:
            rows = adapter.search(q)
            if rows:
                out.extend(rows)
        except Exception:
            continue
    return out


def list_title_search_sources() -> list[dict]:
    return list_sources_by_capability("title_search")

from __future__ import annotations

from urllib.parse import urlparse

from sources.registry import ADAPTERS, GENERIC_DETECTOR


def normalize_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized.startswith(("http://", "https://")):
        normalized = "https://" + normalized
    return normalized


def get_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def resolve_url(url: str):
    normalized = normalize_url(url)
    domain = get_domain(normalized)
    for adapter in ADAPTERS:
        if domain in adapter.domains or adapter.can_handle_url(normalized):
            return adapter.resolve_url(normalized)
    return GENERIC_DETECTOR.resolve_url(normalized)


def search_title(query: str) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    out: list[dict] = []
    for adapter in ADAPTERS:
        try:
            out.extend(adapter.search(q))
        except Exception:
            continue
    return out

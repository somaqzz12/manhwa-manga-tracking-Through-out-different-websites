from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.scraping import is_public_http_url


def normalize_bookmark_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def extract_series_slug(raw_url: str) -> str:
    from services import chapter_parsing as chapter
    return chapter.extract_series_slug(raw_url)


def resolve_series_listing_url(
    url: str,
    *,
    fetch_public_url_cb,
) -> str:
    if not is_public_http_url(url):
        return url
    parsed_slug = extract_series_slug(url)
    low = (url or "").lower()
    if parsed_slug and ("/manga/" in low or "/comics/" in low) and "chapter" not in low and not re.search(r"-\d+(?:\.\d+)?/?$", low):
        return url.rstrip("/")
    try:
        res = fetch_public_url_cb(url)
        res.raise_for_status()
    except Exception:
        return url

    final_url = str(res.url or url).strip()
    soup = BeautifulSoup(res.text, "html.parser")
    candidates: list[str] = []
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        candidates.append(urljoin(final_url or url, canonical.get("href", "").strip()))
    og_url = soup.select_one('meta[property="og:url"]')
    if og_url and og_url.get("content"):
        candidates.append(urljoin(final_url or url, og_url.get("content", "").strip()))
    candidates.append(final_url)
    candidates.append(url)

    def is_chapter_like(raw: str) -> bool:
        path = raw.lower()
        return bool(
            re.search(r"/(?:chapter|ch|episode|ep)[-_ /]?\d", path)
            or re.search(r"/c\d+(?:\.\d+)?(?:/|$)", path)
            or re.search(r"-chapter-\d+(?:\.\d+)?(?:/|$)", path)
            or re.search(r"-\d+(?:\.\d+)?/?$", path)
        )

    candidates = [c for c in candidates if c and is_public_http_url(c)]
    preferred = [c for c in candidates if "/manga/" in c.lower() or "/comics/" in c.lower()]
    if preferred:
        return preferred[0].rstrip("/")

    base_slug = extract_series_slug(url)
    if base_slug:
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            absolute = urljoin(final_url or url, href)
            if not is_public_http_url(absolute):
                continue
            lowered = absolute.lower()
            if "/manga/" not in lowered and "/comics/" not in lowered:
                continue
            href_slug = extract_series_slug(absolute)
            if href_slug and (href_slug == base_slug or base_slug in href_slug or href_slug in base_slug):
                return absolute.rstrip("/")

    for c in candidates:
        if c and not is_chapter_like(c):
            return c.rstrip("/")
    return final_url.rstrip("/") if final_url else url


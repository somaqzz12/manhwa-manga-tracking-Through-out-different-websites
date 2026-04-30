from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

from sources.base import ChapterResult, SourceAdapter, SourcePreview

MANGADEX_API = "https://api.mangadex.org"
MANGADEX_CDN_COVERS = "https://uploads.mangadex.org/covers"


def _cover_url_from_manga(manga_obj: dict, included: list[dict]) -> Optional[str]:
    mid = (manga_obj or {}).get("id")
    if not mid:
        return None
    by_id = {str(i.get("id")): i for i in (included or []) if isinstance(i, dict) and i.get("id")}
    for rel in (manga_obj.get("relationships") or []):
        if rel.get("type") != "cover_art":
            continue
        rel_fn = (rel.get("attributes") or {}).get("fileName")
        if isinstance(rel_fn, str) and rel_fn.strip():
            safe_fn = rel_fn.strip().lstrip("/")
            return f"{MANGADEX_CDN_COVERS}/{mid}/{safe_fn}"
        cid = rel.get("id")
        node = by_id.get(str(cid)) if cid else None
        if not node:
            continue
        fn = (node.get("attributes") or {}).get("fileName")
        if fn and isinstance(fn, str) and mid:
            safe_fn = fn.strip().lstrip("/")
            if safe_fn:
                return f"{MANGADEX_CDN_COVERS}/{mid}/{safe_fn}"
    return None


def _fetch_latest_chapter_meta(manga_id: str, session: requests.Session) -> tuple[Optional[str], Optional[int]]:
    try:
        r = session.get(
            f"{MANGADEX_API}/chapter",
            params={
                "manga": manga_id,
                "translatedLanguage[]": ["en"],
                "limit": 1,
                "order[chapter]": "desc",
            },
            timeout=12,
        )
        r.raise_for_status()
        body = r.json()
        total = body.get("total")
        items = body.get("data") or []
        latest: Optional[str] = None
        if items:
            ch = (items[0].get("attributes") or {}).get("chapter")
            if ch is not None:
                latest = str(ch)
        t_int: Optional[int] = None
        if total is not None:
            try:
                t_int = int(total)
            except (TypeError, ValueError):
                t_int = None
        return latest, t_int
    except Exception:
        return None, None


class MangaDexAdapter(SourceAdapter):
    id = "mangadex"
    name = "MangaDex"
    domains = ["mangadex.org"]
    support_level = "official_api"

    def can_handle_url(self, url: str) -> bool:
        return "mangadex.org" in url.lower()

    def extract_manga_id(self, url: str) -> Optional[str]:
        match = re.search(r"/title/([a-f0-9-]+)", url, flags=re.IGNORECASE)
        return match.group(1) if match else None

    def resolve_url(self, url: str) -> SourcePreview:
        manga_id = self.extract_manga_id(url)
        if not manga_id:
            return SourcePreview(
                source_name=self.name,
                source_url=url,
                support_level=self.support_level,
                confidence=0.3,
                title="Unknown MangaDex title",
                warnings=["Could not extract MangaDex manga ID."],
            )

        session = requests.Session()
        try:
            manga_res = session.get(
                f"{MANGADEX_API}/manga/{manga_id}",
                params={"includes[]": ["cover_art"]},
                timeout=15,
            )
            manga_res.raise_for_status()
            body = manga_res.json()
            manga_data = body.get("data", {})
            included = body.get("included") or []
            attrs = manga_data.get("attributes", {})
            title_map = attrs.get("title") or {}
            title = title_map.get("en") or next(iter(title_map.values()), "Unknown title")
            cover_url = _cover_url_from_manga(manga_data, included)

            chapters_res = session.get(
                f"{MANGADEX_API}/chapter",
                params={
                    "manga": manga_id,
                    "translatedLanguage[]": ["en"],
                    "limit": 100,
                    "order[chapter]": "desc",
                },
                timeout=15,
            )
            chapters_res.raise_for_status()
            ch_json = chapters_res.json()
            chapter_data = ch_json.get("data", [])
        except Exception as exc:
            return SourcePreview(
                source_name=self.name,
                source_url=url,
                support_level=self.support_level,
                confidence=0.25,
                title="MangaDex lookup failed",
                warnings=[f"MangaDex API error: {exc}"],
            )

        chapters: list[ChapterResult] = []
        for item in chapter_data:
            cattrs = item.get("attributes", {})
            chapter_no = cattrs.get("chapter")
            if not chapter_no:
                continue
            chapters.append(
                ChapterResult(
                    number=str(chapter_no),
                    title=cattrs.get("title"),
                    url=f"https://mangadex.org/chapter/{item.get('id', '')}",
                    released_at=cattrs.get("publishAt"),
                )
            )
        latest = chapters[0].number if chapters else None
        ch_total = ch_json.get("total")
        try:
            chapter_count = int(ch_total) if ch_total is not None else (len(chapters) if chapters else None)
        except (TypeError, ValueError):
            chapter_count = len(chapters) if chapters else None
        return SourcePreview(
            source_name=self.name,
            source_url=url,
            support_level=self.support_level,
            confidence=0.95,
            title=title,
            canonical_title=title,
            description=(attrs.get("description") or {}).get("en"),
            latest_chapter=latest,
            cover_url=cover_url,
            chapter_count=chapter_count,
            chapters=chapters,
            warnings=[],
        )

    def search(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        try:
            res = requests.get(
                f"{MANGADEX_API}/manga",
                params={
                    "title": q,
                    "limit": 8,
                    "includes[]": ["cover_art"],
                    "contentRating[]": ["safe", "suggestive"],
                },
                timeout=15,
            )
            res.raise_for_status()
            body = res.json()
            items = body.get("data", [])
            included = body.get("included") or []
        except Exception:
            return []

        session = requests.Session()

        def enrich_one(item: dict) -> dict:
            attrs = item.get("attributes", {})
            title_map = attrs.get("title") or {}
            title = title_map.get("en") or next(iter(title_map.values()), None)
            if not title:
                return {}
            mid = item.get("id", "")
            cover_url = _cover_url_from_manga(item, included)
            latest_chapter: Optional[str] = None
            chapter_count: Optional[int] = None
            if mid:
                latest_chapter, chapter_count = _fetch_latest_chapter_meta(str(mid), session)
            return {
                "source_id": self.id,
                "source_name": self.name,
                "external_id": mid,
                "title": title,
                "url": f"https://mangadex.org/title/{mid}",
                "description": (attrs.get("description") or {}).get("en"),
                "status": attrs.get("status"),
                "confidence": 0.92,
                "cover_url": cover_url or "",
                "latest_chapter": latest_chapter,
                "chapter_count": chapter_count,
                "support_level": self.support_level,
            }

        out: list[dict] = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futs = [pool.submit(enrich_one, item) for item in items]
            for fut in futs:
                row = fut.result()
                if row:
                    out.append(row)
        return out

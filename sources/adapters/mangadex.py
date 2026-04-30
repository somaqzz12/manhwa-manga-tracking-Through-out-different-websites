from __future__ import annotations

import re
from typing import Optional

import requests

from sources.base import ChapterResult, SourceAdapter, SourcePreview


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

        try:
            manga_res = requests.get(f"https://api.mangadex.org/manga/{manga_id}", timeout=15)
            manga_res.raise_for_status()
            manga_data = manga_res.json().get("data", {})
            attrs = manga_data.get("attributes", {})
            title_map = attrs.get("title") or {}
            title = title_map.get("en") or next(iter(title_map.values()), "Unknown title")

            chapters_res = requests.get(
                "https://api.mangadex.org/chapter",
                params={
                    "manga": manga_id,
                    "translatedLanguage[]": ["en"],
                    "limit": 100,
                    "order[chapter]": "desc",
                },
                timeout=15,
            )
            chapters_res.raise_for_status()
            chapter_data = chapters_res.json().get("data", [])
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
        return SourcePreview(
            source_name=self.name,
            source_url=url,
            support_level=self.support_level,
            confidence=0.95,
            title=title,
            canonical_title=title,
            description=(attrs.get("description") or {}).get("en"),
            latest_chapter=latest,
            chapter_count=len(chapters) if chapters else None,
            chapters=chapters,
            warnings=[],
        )

    def search(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        try:
            res = requests.get(
                "https://api.mangadex.org/manga",
                params={"title": q, "limit": 8, "includes[]": ["cover_art"]},
                timeout=15,
            )
            res.raise_for_status()
            items = res.json().get("data", [])
        except Exception:
            return []
        out: list[dict] = []
        for item in items:
            attrs = item.get("attributes", {})
            title_map = attrs.get("title") or {}
            title = title_map.get("en") or next(iter(title_map.values()), None)
            if not title:
                continue
            out.append(
                {
                    "source_id": self.id,
                    "source_name": self.name,
                    "external_id": item.get("id"),
                    "title": title,
                    "url": f"https://mangadex.org/title/{item.get('id', '')}",
                    "description": (attrs.get("description") or {}).get("en"),
                    "status": attrs.get("status"),
                    "confidence": 0.92,
                }
            )
        return out

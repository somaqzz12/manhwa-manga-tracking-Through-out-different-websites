from __future__ import annotations

from urllib.parse import urlparse

from sources.base import ChapterResult, SourceAdapter, SourcePreview


class AsuraAdapter(SourceAdapter):
    id = "asura"
    name = "Asura"
    domains = ["asuracomic.net", "asuratoon.com", "asurascans.com"]
    support_level = "site_adapter"

    def can_handle_url(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower().replace("www.", "")
        return any(d in host for d in self.domains)

    def resolve_url(self, url: str) -> SourcePreview:
        # Lightweight MVP resolver: domain-aware preview without brittle scraping.
        guessed_title = (
            url.rstrip("/")
            .split("/")[-1]
            .replace("-", " ")
            .replace("_", " ")
            .strip()
            .title()
            or "Asura Series"
        )
        return SourcePreview(
            source_name=self.name,
            source_url=url,
            support_level=self.support_level,
            confidence=0.86,
            title=guessed_title,
            latest_chapter=None,
            chapters=[
                ChapterResult(number="?", title="Preview only (adapter stub)", url=url),
            ],
            warnings=["Asura adapter is currently a preview stub; chapter scraping will be added next."],
        )

    def search(self, query: str) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        slug = q.lower().replace(" ", "-")
        return [
            {
                "source_id": self.id,
                "source_name": self.name,
                "external_id": slug,
                "title": q.title(),
                "url": f"https://asuracomic.net/series/{slug}",
                "description": "Community mirror entry",
                "status": None,
                "confidence": 0.72,
            }
        ]

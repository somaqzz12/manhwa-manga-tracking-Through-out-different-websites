from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


SupportLevel = Literal[
    "official_api",
    "site_adapter",
    "generic_detector",
    "manual_only",
    "requested",
    "blocked",
]


@dataclass
class ChapterResult:
    number: str
    title: Optional[str]
    url: str
    released_at: Optional[str] = None


@dataclass
class SourcePreview:
    source_name: str
    source_url: str
    support_level: SupportLevel
    confidence: float
    title: str
    latest_chapter: Optional[str] = None
    cover_url: Optional[str] = None
    description: Optional[str] = None
    chapter_count: Optional[int] = None
    canonical_title: Optional[str] = None
    chapters: list[ChapterResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SourceAdapter:
    id: str
    name: str
    domains: list[str]
    support_level: SupportLevel

    def can_handle_url(self, url: str) -> bool:
        raise NotImplementedError

    def resolve_url(self, url: str) -> SourcePreview:
        raise NotImplementedError

    def search(self, query: str) -> list[dict]:
        return []

    def get_title_details(self, external_id: str) -> dict:
        return {}

    # Backward compatibility with earlier callers.
    def can_handle(self, url: str) -> bool:
        return self.can_handle_url(url)

    def resolve(self, url: str) -> SourcePreview:
        return self.resolve_url(url)

    def check_updates(self, url: str) -> SourcePreview:
        return self.resolve_url(url)

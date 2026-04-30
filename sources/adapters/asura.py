from __future__ import annotations

from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from services import chapter_parsing

from sources.base import ChapterResult, SourceAdapter, SourcePreview
from sources.protection import detect_protected_html


class AsuraAdapter(SourceAdapter):
    id = "asura"
    name = "Asura"
    domains = ["asuracomic.net", "asuratoon.com", "asurascans.com"]
    support_level = "site_adapter"
    _title_selectors = (
        ".post-title h1",
        "h1.entry-title",
        ".series-title h1",
        "h1",
    )
    _cover_selectors = (
        ".thumb img",
        ".summary_image img",
        "img.ts-header-image",
        "meta[property='og:image']",
    )
    _chapter_selectors = (
        ".wp-manga-chapter a",
        ".listing-chapters_wrap a",
        ".chapters a",
        "#chapterlist a",
        "ul li a",
    )
    _headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    def can_handle_url(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower().replace("www.", "")
        return any(d in host for d in self.domains)

    def resolve_url(self, url: str) -> SourcePreview:
        try:
            res = requests.get(url, headers=self._headers, timeout=15)
            if res.status_code in (401, 403, 429):
                return SourcePreview(
                    source_name=self.name,
                    source_url=url,
                    support_level="manual_only",
                    confidence=0.0,
                    title="",
                    warnings=[f"{self.name} returned HTTP {res.status_code}; try manual tracking."],
                )
            hdrs = getattr(res, "headers", {}) or {}
            blocked, reason = detect_protected_html(res.status_code, res.text, dict(hdrs))
            if blocked:
                return SourcePreview(
                    source_name=self.name,
                    source_url=url,
                    support_level="protected",
                    confidence=0.0,
                    title="",
                    warnings=[
                        "This source blocks server-side checks. Use manual tracking or the browser extension.",
                        f"Detection: {reason}",
                    ],
                )
            res.raise_for_status()
        except Exception as exc:
            return SourcePreview(
                source_name=self.name,
                source_url=url,
                support_level="manual_only",
                confidence=0.0,
                title="",
                warnings=[f"Could not fetch Asura page: {exc}"],
            )

        soup = BeautifulSoup(res.text, "html.parser")
        title = self._pick_title(soup) or (
            url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").strip().title() or "Asura Series"
        )
        cover = self._pick_cover(soup, url)
        chapters = self._pick_chapters(soup, url)
        chapters.sort(key=self._chapter_sort_key, reverse=True)
        latest = chapters[0].number if chapters else None
        return SourcePreview(
            source_name=self.name,
            source_url=url,
            support_level=self.support_level if chapters else "manual_only",
            confidence=0.82 if chapters else 0.35,
            title=title,
            canonical_title=title,
            cover_url=cover,
            latest_chapter=latest,
            chapter_count=len(chapters) if chapters else None,
            chapters=chapters,
            warnings=[] if chapters else ["No public chapter list detected; you can still track manually."],
        )

    def search(self, query: str) -> list[dict]:
        """Title search not implemented yet; URL resolve works."""
        return []

    def _pick_title(self, soup: BeautifulSoup) -> str:
        for sel in self._title_selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if text:
                    return text
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return str(og["content"]).strip()
        return ""

    def _pick_cover(self, soup: BeautifulSoup, base_url: str) -> str | None:
        for sel in self._cover_selectors:
            for el in soup.select(sel):
                if el.name == "meta" and el.get("content"):
                    return urljoin(base_url, str(el.get("content")).strip())
                if el.name == "img":
                    src = (el.get("src") or el.get("data-src") or "").strip()
                    if src:
                        return urljoin(base_url, src)
        return None

    def _pick_chapters(self, soup: BeautifulSoup, base_url: str) -> list[ChapterResult]:
        out: list[ChapterResult] = []
        seen: set[str] = set()
        for sel in self._chapter_selectors:
            for anchor in soup.select(sel):
                if anchor.name != "a":
                    continue
                href = (anchor.get("href") or "").strip()
                if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                    continue
                abs_url = urljoin(base_url, href)
                if abs_url in seen:
                    continue
                txt = anchor.get_text(" ", strip=True)
                num = self._chapter_num(txt, abs_url)
                if not num:
                    continue
                seen.add(abs_url)
                out.append(ChapterResult(number=num, title=txt or None, url=abs_url))
        return out[:220]

    def _chapter_num(self, text: str, href: str) -> str | None:
        num = chapter_parsing.parse_chapter_number(text or "")
        if num is None:
            num = chapter_parsing.parse_chapter_from_url(href or "")
        if num is None:
            return None
        return str(int(num)) if num == int(num) else str(num)

    def _chapter_sort_key(self, ch: ChapterResult) -> float:
        num = chapter_parsing.parse_chapter_number(ch.number or "")
        return float(num) if num is not None else -1.0

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from sources.base import ChapterResult, SourceAdapter, SourcePreview


class GenericDetector(SourceAdapter):
    id = "generic"
    name = "Unknown Site"
    domains: list[str] = []
    support_level = "generic_detector"

    def can_handle_url(self, url: str) -> bool:
        return True

    def resolve_url(self, url: str) -> SourcePreview:
        try:
            res = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 MangaTrackerBot/1.0"},
                timeout=15,
            )
            res.raise_for_status()
        except Exception as exc:
            return SourcePreview(
                source_name="Unknown Site",
                source_url=url,
                support_level="manual_only",
                confidence=0.0,
                title="",
                warnings=[f"Could not fetch page: {exc}"],
            )

        soup = BeautifulSoup(res.text, "html.parser")
        title = self.detect_title(soup) or ""
        description = self.detect_description(soup)
        cover_url = self.detect_cover(soup)
        chapters = self.detect_chapters(soup, url)
        latest = chapters[0].number if chapters else None

        return SourcePreview(
            source_name="Unknown Site",
            source_url=url,
            support_level="generic_detector" if chapters else "manual_only",
            confidence=0.55 if chapters else 0.2,
            title=title,
            canonical_title=title or None,
            description=description,
            cover_url=cover_url,
            latest_chapter=latest,
            chapter_count=len(chapters) if chapters else None,
            chapters=chapters,
            warnings=[] if chapters else ["Could not detect chapter list. Manual tracking available."],
        )

    def detect_title(self, soup: BeautifulSoup) -> str | None:
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        if soup.title:
            return soup.title.get_text(strip=True)
        return None

    def detect_description(self, soup: BeautifulSoup) -> str | None:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            return og_desc["content"].strip()
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()
        return None

    def detect_cover(self, soup: BeautifulSoup) -> str | None:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return og_img["content"].strip()
        return None

    def detect_chapters(self, soup: BeautifulSoup, base_url: str) -> list[ChapterResult]:
        candidates: list[ChapterResult] = []
        selectors = [
            ".wp-manga-chapter a",
            ".listing-chapters_wrap a",
            ".chapter-list a",
            ".eph-num a",
            ".bixbox a",
            "a[href*='chapter']",
            "a[href*='episode']",
        ]
        for selector in selectors:
            for a in soup.select(selector):
                text = a.get_text(" ", strip=True)
                href = a.get("href")
                if not href:
                    continue
                num = self.extract_chapter_number(text, href)
                if not num:
                    continue
                candidates.append(
                    ChapterResult(number=num, title=text or None, url=urljoin(base_url, href))
                )
        seen: set[str] = set()
        unique: list[ChapterResult] = []
        for chapter in candidates:
            if chapter.url in seen:
                continue
            seen.add(chapter.url)
            unique.append(chapter)
        return unique[:200]

    def extract_chapter_number(self, text: str, href: str) -> str | None:
        combined = f"{text} {href}".lower()
        for pattern in [
            r"chapter[\s\-_/]*(\d+(?:\.\d+)?)",
            r"ch[\s\-_/]*(\d+(?:\.\d+)?)",
            r"episode[\s\-_/]*(\d+(?:\.\d+)?)",
            r"ep[\s\-_/]*(\d+(?:\.\d+)?)",
        ]:
            match = re.search(pattern, combined)
            if match:
                return match.group(1)
        return None

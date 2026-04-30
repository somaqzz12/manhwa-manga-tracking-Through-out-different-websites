from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services import chapter_parsing
from sources.base import ChapterResult, SourceAdapter, SourcePreview

UA = "Mozilla/5.0 MangaTrackerBot/1.0 (+https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites)"


def is_valid_metadata_img_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u or u.startswith("data:") or u.startswith("javascript:"):
        return False
    if u.endswith(".svg") or "spacer" in u or "pixel" in u or "tracking" in u:
        return False
    if u.startswith("//"):
        return True
    return u.startswith("http")


def absolutize_media_url(raw: str, base_url: str) -> str | None:
    v = (raw or "").strip()
    if not v:
        return None
    if v.startswith("//"):
        v = "https:" + v
    out = urljoin(base_url, v)
    return out if is_valid_metadata_img_url(out) else None


def img_candidate_urls(tag, base_url: str) -> list[str]:
    out: list[str] = []
    if not tag:
        return out
    for attr in ("src", "data-src", "data-lazy-src", "data-original", "data-srcset"):
        raw = tag.get(attr)
        if not raw:
            continue
        if attr == "data-srcset":
            part = (raw.split(",")[0] or "").strip().split()[0]
            u = absolutize_media_url(part, base_url)
        else:
            u = absolutize_media_url(raw, base_url)
        if u:
            out.append(u)
    return out


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
                headers={"User-Agent": UA},
                timeout=15,
            )
            if res.status_code in (401, 403, 429):
                return SourcePreview(
                    source_name="Unknown Site",
                    source_url=url,
                    support_level="manual_only",
                    confidence=0.0,
                    title="",
                    warnings=[f"Site returned HTTP {res.status_code}; automatic metadata is unavailable."],
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
        cover_url = self.detect_cover(soup, url)
        chapters = self.detect_chapters(soup, url)
        latest = chapters[0].number if chapters else None

        return SourcePreview(
            source_name="Unknown Site",
            source_url=url,
            support_level="generic_detector" if chapters else "manual_only",
            confidence=0.32 if chapters else 0.12,
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

    def detect_cover(self, soup: BeautifulSoup, base_url: str) -> str | None:
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            u = absolutize_media_url(og["content"], base_url)
            if u:
                return u
        tw = soup.find("meta", attrs={"name": re.compile(r"^twitter:image$", re.I)})
        if tw and tw.get("content"):
            u = absolutize_media_url(tw["content"], base_url)
            if u:
                return u
        for sel in (
            ".summary_image img",
            ".thumb img",
            ".cover img",
            ".info-cover img",
            ".info-image img",
            ".info_image img",
            ".series-cover img",
            ".series_cover img",
            "picture img",
        ):
            for img in soup.select(sel):
                for u in img_candidate_urls(img, base_url):
                    return u
        for img in soup.select('img[alt*="cover" i], img[title*="cover" i]'):
            for u in img_candidate_urls(img, base_url):
                return u
        return None

    def detect_chapters(self, soup: BeautifulSoup, base_url: str) -> list[ChapterResult]:
        candidates: list[ChapterResult] = []
        selectors = [
            ".wp-manga-chapter a",
            ".listing-chapters_wrap a",
            ".chapter-list a",
            ".chapterlist a",
            ".eph-num a",
            ".bixbox a",
            ".chapter-item a",
            "a[href*='chapter']",
            "a[href*='episode']",
        ]
        for selector in selectors:
            for a in soup.select(selector):
                text = a.get_text(" ", strip=True)
                href = a.get("href")
                if not href:
                    continue
                abs_url = urljoin(base_url, href)
                num = self.extract_chapter_number(text, abs_url)
                if not num:
                    continue
                candidates.append(
                    ChapterResult(number=num, title=text or None, url=abs_url)
                )
        seen: set[str] = set()
        unique: list[ChapterResult] = []
        for chapter in candidates:
            if chapter.url in seen:
                continue
            seen.add(chapter.url)
            unique.append(chapter)

        def sort_key(ch: ChapterResult) -> float:
            n = chapter_parsing.parse_chapter_number(ch.number or "") or chapter_parsing.parse_chapter_from_url(
                ch.url or ""
            )
            return float(n) if n is not None else -1.0

        unique.sort(key=sort_key, reverse=True)
        return unique[:200]

    def extract_chapter_number(self, text: str, href: str) -> str | None:
        pn = chapter_parsing.parse_chapter_number(text or "")
        if pn is not None:
            return str(int(pn)) if pn == int(pn) else str(pn)
        pu = chapter_parsing.parse_chapter_from_url(href or "")
        if pu is not None:
            return str(int(pu)) if pu == int(pu) else str(pu)
        combined = f"{text} {href}".lower()
        for pattern in [
            r"chapter[\s\-_/]*(\d+(?:\.\d+)?)",
            r"ch[\s.\-_/]*(\d+(?:\.\d+)?)",
            r"episode[\s\-_/]*(\d+(?:\.\d+)?)",
            r"ep[\s.\-_/]*(\d+(?:\.\d+)?)",
            r"(?:^|/)(?:c|ch)[-_](\d+(?:\.\d+)?)(?:/|$)",
        ]:
            match = re.search(pattern, combined)
            if match:
                return match.group(1)
        return None

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from services import chapter_parsing
from sources.base import ChapterResult, SourceAdapter, SourcePreview
from sources.generic_detector import absolutize_media_url, img_candidate_urls

UA = "Mozilla/5.0 MangaTrackerBot/1.0 (+https://github.com/somaqzz12/manhwa-manga-tracking-Through-out-different-websites)"


def _split_selectors(csv: str) -> list[str]:
    return [s.strip() for s in (csv or "").split(",") if s.strip()]


class CssSourceAdapter(SourceAdapter):
    """HTML/CSS selector driven resolver for curated catalog sources."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.id = str(profile.get("id") or "css_source")
        self.name = str(profile.get("display_name") or self.id)
        raw_domains = profile.get("domains") or []
        self.domains = [str(d).lower().strip() for d in raw_domains if str(d).strip()]
        sl = str(profile.get("support_level") or "site_adapter").strip().lower()
        if sl not in ("site_adapter", "generic_detector", "manual_only"):
            sl = "site_adapter"
        self.support_level = sl  # type: ignore[assignment]
        self._title_sel = str(profile.get("title_selector") or "h1")
        self._cover_sel = str(profile.get("cover_selector") or "")
        self._chapter_sel = str(profile.get("chapter_link_selector") or "a[href*='chapter']")

    def can_handle_url(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        if ":" in host and not host.startswith("["):
            host = host.split(":")[0]
        for d in self.domains:
            if host == d or host.endswith("." + d):
                return True
        return False

    def search(self, query: str) -> list[dict]:
        return []

    def resolve_url(self, url: str) -> SourcePreview:
        try:
            res = requests.get(url, headers={"User-Agent": UA}, timeout=15)
            if res.status_code in (401, 403, 429):
                return SourcePreview(
                    source_name=self.name,
                    source_url=url,
                    support_level="manual_only",
                    confidence=0.0,
                    title="",
                    warnings=[f"{self.name} returned HTTP {res.status_code}; try Add URL manually."],
                )
            res.raise_for_status()
        except Exception as exc:
            return SourcePreview(
                source_name=self.name,
                source_url=url,
                support_level="manual_only",
                confidence=0.0,
                title="",
                warnings=[f"Could not fetch series page: {exc}"],
            )

        soup = BeautifulSoup(res.text, "html.parser")
        title = self._pick_title(soup, url)
        description = self._pick_description(soup)
        cover_url = self._pick_cover(soup, url)
        chapters = self._pick_chapters(soup, url)
        chapters.sort(key=self._chapter_sort_key, reverse=True)
        latest = chapters[0].number if chapters else None

        return SourcePreview(
            source_name=self.name,
            source_url=url,
            support_level=self.support_level if chapters else "manual_only",
            confidence=0.78 if chapters else 0.35,
            title=title or "",
            canonical_title=title or None,
            description=description,
            cover_url=cover_url,
            latest_chapter=latest,
            chapter_count=len(chapters) if chapters else None,
            chapters=chapters,
            warnings=[] if chapters else [f"{self.name}: no public chapter list detected; manual tracking only."],
        )

    def _pick_title(self, soup: BeautifulSoup, base_url: str) -> str:
        for sel in _split_selectors(self._title_sel):
            if sel.lower().startswith("meta"):
                continue
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if t:
                    return t
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
        if soup.title:
            return soup.title.get_text(strip=True)
        return ""

    def _pick_description(self, soup: BeautifulSoup) -> str | None:
        og = soup.find("meta", property="og:description")
        if og and og.get("content"):
            return og["content"].strip()[:2000]
        m = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if m and m.get("content"):
            return m["content"].strip()[:2000]
        return None

    def _pick_cover(self, soup: BeautifulSoup, base_url: str) -> str | None:
        for sel in _split_selectors(self._cover_sel):
            if "og:image" in sel:
                og = soup.find("meta", property="og:image")
                if og and og.get("content"):
                    u = absolutize_media_url(og["content"], base_url)
                    if u:
                        return u
                continue
            for el in soup.select(sel):
                if el.name == "meta" and el.get("content"):
                    u = absolutize_media_url(el["content"], base_url)
                    if u:
                        return u
                    continue
                if el.name == "img":
                    for u in img_candidate_urls(el, base_url):
                        return u
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            u = absolutize_media_url(og["content"], base_url)
            if u:
                return u
        return None

    def _pick_chapters(self, soup: BeautifulSoup, base_url: str) -> list[ChapterResult]:
        out: list[ChapterResult] = []
        seen: set[str] = set()
        for sel in _split_selectors(self._chapter_sel):
            for a in soup.select(sel):
                if a.name != "a":
                    continue
                href = (a.get("href") or "").strip()
                if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                    continue
                abs_u = urljoin(base_url, href)
                text = a.get_text(" ", strip=True)
                num = self._chapter_num(text, abs_u)
                if not num:
                    continue
                if abs_u in seen:
                    continue
                seen.add(abs_u)
                out.append(ChapterResult(number=num, title=text or None, url=abs_u))
        return out[:220]

    def _chapter_num(self, text: str, href: str) -> str | None:
        pn = chapter_parsing.parse_chapter_number(text or "")
        if pn is not None:
            return str(int(pn)) if pn == int(pn) else str(pn)
        pu = chapter_parsing.parse_chapter_from_url(href or "")
        if pu is not None:
            return str(int(pu)) if pu == int(pu) else str(pu)
        return None

    def _chapter_sort_key(self, ch: ChapterResult) -> float:
        n = chapter_parsing.parse_chapter_number(ch.number or "") or chapter_parsing.parse_chapter_from_url(ch.url or "")
        return float(n) if n is not None else -1.0


def load_css_adapters_from_profiles(path: Path) -> list[CssSourceAdapter]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    adapters: list[CssSourceAdapter] = []
    for row in raw:
        if isinstance(row, dict) and row.get("id") and row.get("domains"):
            adapters.append(CssSourceAdapter(row))
    return adapters

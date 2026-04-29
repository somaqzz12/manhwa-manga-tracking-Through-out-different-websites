import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

CHAPTER_PATTERN = re.compile(r"(chapter|ch\.?|ep\.?|episode)\s*[:#-]?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
URL_CHAPTER_PATTERN = re.compile(r"(?:^|[^a-z])(c|chapter|ch|episode|ep)[-_ ]?(\d+(?:\.\d+)?)$", re.IGNORECASE)
URL_CHAPTER_STEP_PATTERN = re.compile(r"^(chapter|ch|episode|ep)$", re.IGNORECASE)


def parse_chapter_number(text: str) -> Optional[float]:
    match = CHAPTER_PATTERN.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(2))
    except ValueError:
        return None


def parse_chapter_from_url(url: str) -> Optional[float]:
    raw_url = (url or "").strip()
    if not raw_url:
        return None
    path = raw_url
    if "://" in raw_url:
        try:
            path = urlparse(raw_url).path
        except Exception:
            path = raw_url
    tokens = [t for t in path.strip("/").split("/") if t]
    if not tokens:
        return None
    if len(tokens) >= 2 and URL_CHAPTER_STEP_PATTERN.match(tokens[-2]):
        try:
            return float(tokens[-1])
        except ValueError:
            pass
    tail = tokens[-1]
    match = URL_CHAPTER_PATTERN.search(tail)
    if not match:
        match = re.search(r"(?:chapter|ch|episode|ep)[^0-9]{0,3}(\d+(?:\.\d+)?)", path, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    try:
        return float(match.group(2))
    except ValueError:
        return None


def extract_series_slug(raw_url: str) -> str:
    try:
        path = urlparse(raw_url).path.strip("/")
    except Exception:
        path = (raw_url or "").strip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return ""
    if parts[0].lower() in {"manga", "comics"} and len(parts) >= 2:
        slug = parts[1]
    else:
        slug = parts[-1]
    slug = re.sub(r"-chapter-\d+(?:\.\d+)?$", "", slug, flags=re.IGNORECASE)
    slug = re.sub(r"[-_]\d+(?:\.\d+)?$", "", slug, flags=re.IGNORECASE)
    return slug.lower()


def iter_chapter_candidates(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        abs_href = urljoin(page_url, href)
        label = a.get_text(" ", strip=True) or ""
        class_text = " ".join(a.get("class", [])) if a.get("class") else ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, class_text))
    for opt in soup.select("option[value]"):
        value = (opt.get("value") or "").strip()
        if not value or value.startswith("#"):
            continue
        abs_href = urljoin(page_url, value)
        label = opt.get_text(" ", strip=True) or ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, "option"))
    for node in soup.select("[data-href], [data-url], [data-link]"):
        raw = (node.get("data-href") or node.get("data-url") or node.get("data-link") or "").strip()
        if not raw:
            continue
        abs_href = urljoin(page_url, raw)
        label = node.get_text(" ", strip=True) or ""
        class_text = " ".join(node.get("class", [])) if node.get("class") else ""
        key = (label, abs_href)
        if key in seen:
            continue
        seen.add(key)
        out.append((label, abs_href, class_text))
    return out


def pick_best_candidate_with_debug(soup: BeautifulSoup, page_url: str) -> dict:
    page_slug = extract_series_slug(page_url)
    best_label: Optional[str] = None
    best_num: Optional[float] = None
    best_url: Optional[str] = None
    best_score = -1
    parser_hits = {"anchors": 0, "options": 0, "data_attrs": 0}
    candidate_debug: list[dict] = []
    error_flags: list[str] = []
    for text, absolute_href, class_text in iter_chapter_candidates(soup, page_url):
        if "option" in class_text:
            parser_hits["options"] += 1
        elif "data-" in class_text:
            parser_hits["data_attrs"] += 1
        else:
            parser_hits["anchors"] += 1
        if not text or len(text) > 140:
            continue
        parsed_from_text = parse_chapter_number(text)
        parsed_from_url = parse_chapter_from_url(absolute_href)
        if parsed_from_text is None and parsed_from_url is None:
            continue
        final_num = parsed_from_text if parsed_from_text is not None else parsed_from_url
        if final_num is None:
            continue
        href_slug = extract_series_slug(absolute_href) if absolute_href else ""
        score = 0
        if parsed_from_url is not None:
            score += 3
        if re.search(r"chapter|episode|list|item", class_text, re.IGNORECASE):
            score += 2
        if page_slug and href_slug:
            if page_slug == href_slug or page_slug in absolute_href.lower():
                score += 5
            else:
                continue
        score += int(final_num)
        candidate_debug.append(
            {
                "label": text,
                "url": absolute_href,
                "chapter_num": final_num,
                "score": score,
                "same_series": bool(not page_slug or (href_slug and (href_slug == page_slug or page_slug in absolute_href.lower()))),
            }
        )
        if score > best_score or (score == best_score and (best_num is None or final_num > best_num)):
            best_score = score
            best_label = text
            best_num = final_num
            best_url = absolute_href or None
    if not candidate_debug:
        error_flags.append("no_chapter_candidates")
    elif len(candidate_debug) > 400:
        error_flags.append("high_candidate_volume")
    confidence = 0.0
    if best_num is not None:
        confidence = 0.55
        if best_url and page_slug and page_slug in best_url.lower():
            confidence += 0.2
        if candidate_debug:
            top_scores = sorted([c["score"] for c in candidate_debug], reverse=True)
            if len(top_scores) == 1:
                confidence += 0.2
            else:
                gap = top_scores[0] - top_scores[1]
                if gap >= 6:
                    confidence += 0.2
                elif gap >= 3:
                    confidence += 0.12
                else:
                    confidence += 0.05
        if best_url and parse_chapter_from_url(best_url) is not None:
            confidence += 0.08
    confidence = max(0.0, min(0.99, round(confidence, 2)))
    if parser_hits["options"] > 0:
        parser_version = "generic-option-list"
    elif parser_hits["data_attrs"] > 0:
        parser_version = "generic-data-attrs"
    else:
        parser_version = "generic-anchor-list"
    if best_label is None:
        fallback_title = soup.title.string.strip() if soup.title and soup.title.string else "No chapter pattern found"
        best_label = fallback_title
    return {
        "label": best_label,
        "chapter_num": best_num,
        "chapter_url": best_url,
        "confidence": confidence,
        "parser_version": parser_version,
        "candidates": sorted(candidate_debug, key=lambda c: c["score"], reverse=True),
        "error_flags": error_flags,
    }


def pick_best_candidate(soup: BeautifulSoup, page_url: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    info = pick_best_candidate_with_debug(soup, page_url)
    return info["label"], info["chapter_num"], info["chapter_url"]

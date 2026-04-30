from __future__ import annotations

import re


def detect_protected_html(status_code: int, html: str, headers: dict | None = None) -> tuple[bool, str]:
    text = (html or "").lower()
    if status_code in {403, 429, 503}:
        return True, f"http_{status_code}"
    markers = (
        "cf-challenge",
        "cloudflare",
        "attention required",
        "captcha",
        "verify you are human",
        "enable javascript",
        "please turn javascript on",
        "ddos protection",
    )
    if any(m in text for m in markers):
        return True, "challenge_or_captcha"
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 40 and ("<html" in text or "<body" in text):
        return True, "empty_or_suspicious_html"
    ct = ((headers or {}).get("Content-Type") or "").lower()
    if ct and "text/html" not in ct and "application/xhtml+xml" not in ct:
        return True, "unexpected_content_type"
    return False, ""


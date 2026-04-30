from __future__ import annotations

import re

from services.library_model import normalize_title, slugify_title


def compact_key(title_or_norm: str) -> str:
    """Collapse spacing/punctuation for fuzzy match (e.g. onepiece vs one piece)."""
    t = normalize_title(title_or_norm) if title_or_norm else ""
    return re.sub(r"[^a-z0-9]+", "", t)


def search_needles(query: str) -> tuple[str, str]:
    """Return (space-normalized key, compact key) for SQL matching."""
    n = normalize_title(query)
    return n, compact_key(query)

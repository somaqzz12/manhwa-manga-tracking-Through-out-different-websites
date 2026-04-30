"""Load and query the manga/manhwa source registry (JSON-driven, scalable)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
APP_ROOT = PACKAGE_DIR.parent

_REGISTRY_LOCK = threading.Lock()
_SOURCES_NEVER_LOADED = object()
_SOURCES_MTIME: Any = _SOURCES_NEVER_LOADED
_SOURCES_PAYLOAD: tuple[list[dict], list[tuple[str, dict]]] = ([], [])
_HEALTH_MTIME: Optional[float] = None
_HEALTH_CACHE: dict = {}


def _env_sources_dir() -> Path:
    import os

    raw = (os.getenv("SOURCES_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return APP_ROOT / "sources"


def _env_legacy_sources_json() -> Optional[Path]:
    import os

    raw = (os.getenv("SOURCES_JSON_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    legacy = APP_ROOT / "sources.json"
    return legacy if legacy.is_file() else None


def _health_path() -> Path:
    return _env_sources_dir() / "_health.json"


def _normalize_registry_host(netloc: str) -> str:
    h = (netloc or "").lower().split(":")[0].strip(".")
    changed = True
    while changed:
        changed = False
        for prefix in ("www.", "www2.", "m.", "mobile."):
            if h.startswith(prefix):
                h = h[len(prefix) :]
                changed = True
                break
    return h


def _coerce_domains(raw: dict) -> list[str]:
    d = raw.get("domains")
    if d is None and raw.get("domain"):
        d = [raw["domain"]]
    if d is None and raw.get("baseUrl"):
        parsed = urlparse(str(raw.get("baseUrl")).strip())
        if parsed.netloc:
            d = [parsed.netloc]
    if d is None:
        return []
    if isinstance(d, str):
        d = [d]
    out: list[str] = []
    for x in d:
        s = str(x).strip().lower().lstrip(".")
        if s and s not in out:
            out.append(s)
    return out


def _derive_id(raw: dict, domains: list[str]) -> str:
    sid = (raw.get("id") or "").strip()
    if sid:
        return sid
    if domains:
        return domains[0].replace(".", "_")
    return "unknown"


def normalize_source_record(raw: dict) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    domains = _coerce_domains(raw)
    sid = _derive_id(raw, domains)
    if not domains:
        log.warning('source "%s" has no domains; skipped', sid)
        return None

    strategy = (raw.get("parsing_strategy") or "css_chapter_links").strip()
    chapter_sel = (raw.get("chapter_link_selector") or raw.get("chapter_selector") or "").strip()
    status = (raw.get("status") or "partial").strip().lower()
    if status in ("unknown", "untested"):
        status = "partial"

    page_type = (raw.get("page_type") or raw.get("type") or "series").strip().lower()

    return {
        **raw,
        "id": sid,
        "display_name": (raw.get("display_name") or sid.replace("_", " ").title()).strip(),
        "domains": domains,
        "status": status,
        "language": (raw.get("language") or "en").strip(),
        "content_type": (raw.get("content_type") or "mixed").strip().lower(),
        "title_selector": (raw.get("title_selector") or "").strip(),
        "cover_selector": (raw.get("cover_selector") or "").strip(),
        "chapter_link_selector": chapter_sel,
        "chapter_selector": chapter_sel,
        "chapter_number_strategy": (raw.get("chapter_number_strategy") or "link_text_href").strip(),
        "parsing_strategy": strategy,
        "page_type": page_type,
        "needs_js": bool(raw.get("needs_js", False)),
        "notes": (raw.get("notes") or "").strip(),
        "sample_series_url": (raw.get("sample_series_url") or "").strip(),
        "nsfw": bool(raw.get("nsfw", False)),
        "extension": (raw.get("extension") or "").strip(),
        "package": (raw.get("package") or "").strip(),
        "version": (raw.get("version") or "").strip(),
        "api": strategy == "mangadex_api",
    }


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_tachiyomi_manifest(payload: Any) -> list[dict]:
    out: list[dict] = []
    if not isinstance(payload, list):
        return out
    for ext in payload:
        if not isinstance(ext, dict):
            continue
        ext_name = str(ext.get("name") or ext.get("extension") or "").strip()
        pkg = str(ext.get("pkg") or ext.get("package") or "").strip()
        apk = str(ext.get("apk") or "").strip()
        ver = str(ext.get("version") or "").strip()
        ext_lang = str(ext.get("lang") or ext.get("language") or "").strip()
        nsfw = bool(ext.get("nsfw", False))
        srcs = ext.get("sources")
        if not isinstance(srcs, list):
            continue
        for src in srcs:
            if not isinstance(src, dict):
                continue
            base = str(src.get("baseUrl") or "").strip()
            sid = str(src.get("id") or "").strip()
            host = _normalize_registry_host(urlparse(base).netloc) if base else ""
            if not host:
                continue
            derived_id = sid or host.replace(".", "_")
            if pkg:
                derived_id = f"{pkg}:{derived_id}"
            out.append(
                {
                    "id": derived_id,
                    "display_name": str(src.get("name") or ext_name or host).strip(),
                    "domains": [host],
                    "status": "partial",
                    "language": str(src.get("lang") or ext_lang or "all").strip(),
                    "content_type": "mixed",
                    "title_selector": "",
                    "cover_selector": "",
                    "chapter_link_selector": "",
                    "chapter_number_strategy": "link_text_href",
                    "parsing_strategy": "css_chapter_links",
                    "page_type": "series",
                    "needs_js": False,
                    "notes": "",
                    "sample_series_url": "",
                    "baseUrl": base,
                    "source_id": sid,
                    "extension": ext_name,
                    "package": pkg,
                    "apk": apk,
                    "version": ver,
                    "nsfw": nsfw,
                }
            )
    return out


def _collect_source_dicts_from_dir(sources_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not sources_dir.is_dir():
        return out
    manifest_path = sources_dir / "sources.manifest.json"
    if manifest_path.is_file():
        try:
            payload = _load_json_file(manifest_path)
            return _flatten_tachiyomi_manifest(payload)
        except Exception as exc:
            log.error("failed to read %s: %s", manifest_path, exc)
            return []
    for path in sorted(sources_dir.glob("*.json")):
        name = path.name.lower()
        if name.startswith("_") or name in ("health.json", "sources.manifest.json"):
            continue
        try:
            payload = _load_json_file(path)
        except Exception as exc:
            log.error("failed to read %s: %s", path, exc)
            continue
        if isinstance(payload, dict) and isinstance(payload.get("sources"), list):
            for item in payload["sources"]:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(payload, list):
            out.extend(_flatten_tachiyomi_manifest(payload))
        elif isinstance(payload, dict) and "id" in payload:
            out.append(payload)
    return out


def _load_catalog() -> list[dict]:
    sources_dir = _env_sources_dir()
    records: list[dict] = []

    dir_records = _collect_source_dicts_from_dir(sources_dir)
    if dir_records:
        records = dir_records
    else:
        legacy = _env_legacy_sources_json()
        if legacy and legacy.is_file():
            try:
                payload = _load_json_file(legacy)
                arr = payload.get("sources") if isinstance(payload, dict) else None
                if isinstance(arr, list):
                    records = [x for x in arr if isinstance(x, dict)]
            except Exception as exc:
                log.error("legacy sources.json failed (%s): %s", legacy, exc)

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for raw in records:
        norm = normalize_source_record(raw)
        if not norm:
            continue
        if norm["id"] in seen_ids:
            log.warning("duplicate source id %s; skipping duplicate", norm["id"])
            continue
        seen_ids.add(norm["id"])
        normalized.append(norm)

    domain_rows: list[tuple[str, dict]] = []
    for rec in normalized:
        for d in rec["domains"]:
            domain_rows.append((d, rec))
    domain_rows.sort(key=lambda x: len(x[0]), reverse=True)
    return normalized, domain_rows


def _reload_if_needed() -> None:
    global _SOURCES_MTIME, _SOURCES_PAYLOAD
    sources_dir = _env_sources_dir()
    try:
        mtimes = []
        if sources_dir.is_dir():
            for path in sources_dir.glob("*.json"):
                if path.name.lower().startswith("_"):
                    continue
                mtimes.append(path.stat().st_mtime)
        legacy = _env_legacy_sources_json()
        if legacy and legacy.is_file():
            mtimes.append(legacy.stat().st_mtime)
        mtime = max(mtimes) if mtimes else None
    except OSError:
        mtime = None

    with _REGISTRY_LOCK:
        if mtime == _SOURCES_MTIME and _SOURCES_MTIME is not _SOURCES_NEVER_LOADED:
            return
        _SOURCES_MTIME = mtime
        _SOURCES_PAYLOAD = _load_catalog()
        log.info("source registry: %d source(s) loaded", len(_SOURCES_PAYLOAD[0]))


def list_sources() -> list[dict]:
    _reload_if_needed()
    return list(_SOURCES_PAYLOAD[0])


def domain_index() -> list[tuple[str, dict]]:
    _reload_if_needed()
    return list(_SOURCES_PAYLOAD[1])


def get_profile_for_url(url: str) -> Optional[dict]:
    try:
        host = _normalize_registry_host(urlparse(url).netloc)
    except Exception:
        return None
    if not host:
        return None
    best: Optional[dict] = None
    best_len = -1
    for domain, profile in domain_index():
        if host == domain or host.endswith("." + domain):
            if len(domain) > best_len:
                best_len = len(domain)
                best = profile
    return best


def load_health() -> dict:
    global _HEALTH_MTIME, _HEALTH_CACHE
    path = _health_path()
    with _REGISTRY_LOCK:
        try:
            mtime = path.stat().st_mtime if path.is_file() else None
        except OSError:
            mtime = None
        if mtime != _HEALTH_MTIME:
            _HEALTH_MTIME = mtime
            if mtime is None:
                _HEALTH_CACHE = {}
            else:
                try:
                    _HEALTH_CACHE = _load_json_file(path)
                except Exception as exc:
                    log.error("failed to read health file %s: %s", path, exc)
                    _HEALTH_CACHE = {}
        return dict(_HEALTH_CACHE) if isinstance(_HEALTH_CACHE, dict) else {}


def sources_with_health() -> list[dict]:
    health = load_health()
    by_id = health.get("by_id") if isinstance(health.get("by_id"), dict) else {}
    updated_at = health.get("updated_at")
    rows = []
    for src in list_sources():
        row = dict(src)
        row["health"] = dict(by_id.get(src["id"], {})) if isinstance(by_id.get(src["id"]), dict) else {}
        row["last_tested_at"] = row["health"].get("checked_at") or updated_at
        rows.append(row)
    return rows


def aggregate_status_counts(sources: Optional[list[dict]] = None) -> dict[str, int]:
    srcs = sources or list_sources()
    health = load_health()
    by_id = health.get("by_id") if isinstance(health.get("by_id"), dict) else {}
    counts = {"total": len(srcs), "working": 0, "partial": 0, "broken": 0}
    for s in srcs:
        hid = s["id"]
        h = by_id.get(hid) if isinstance(by_id.get(hid), dict) else {}
        check_status = (h.get("check_status") or "").strip().lower()
        declared = (s.get("status") or "partial").strip().lower()
        if check_status in ("working", "partial", "broken"):
            effective = check_status
        elif declared in ("working", "partial", "broken"):
            effective = declared
        else:
            effective = "partial"
        if effective == "working":
            counts["working"] += 1
        elif effective == "broken":
            counts["broken"] += 1
        else:
            counts["partial"] += 1
    return counts


def public_api_snapshot() -> dict[str, Any]:
    """Minimal, cache-friendly payload for ``GET /api/registry/public``."""
    health = load_health()
    by_id = health.get("by_id") if isinstance(health.get("by_id"), dict) else {}
    domains: set[str] = set()
    sources: list[dict] = []
    for rec in list_sources():
        for d in rec.get("domains") or []:
            domains.add(str(d).strip().lower())
        hid = rec["id"]
        h = by_id.get(hid) if isinstance(by_id.get(hid), dict) else {}
        check_status = (h.get("check_status") or "").strip().lower()
        declared = (rec.get("status") or "partial").strip().lower()
        if check_status in ("working", "partial", "broken"):
            effective = check_status
        elif declared in ("working", "partial", "broken"):
            effective = declared
        else:
            effective = "partial"
        sources.append(
            {
                "id": hid,
                "domains": rec.get("domains") or [],
                "display_name": rec.get("display_name") or hid,
                "status": effective,
            }
        )
    return {
        "updated_at": health.get("updated_at"),
        "domains": sorted(domains),
        "sources": sources,
        "source_count": len(sources),
    }


def write_health(payload: dict) -> Path:
    path = _health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    global _HEALTH_MTIME, _HEALTH_CACHE
    with _REGISTRY_LOCK:
        _HEALTH_MTIME = path.stat().st_mtime
        _HEALTH_CACHE = dict(payload)
    return path

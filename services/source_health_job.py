"""Shared catalog health probing (CLI cron + optional in-app scheduler)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def run_and_write_health(*, print_summary: bool = False) -> dict[str, Any]:
    """Probe each registry source sample URL and write ``sources/_health.json``."""
    import app as app_module  # noqa: F401 — registers scrape session
    from services import source_registry

    source_registry.list_sources()
    rows: list[tuple[str, str, str | None, str | None]] = []
    by_id: dict = {}

    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    for src in source_registry.list_sources():
        sid = src["id"]
        sample = (src.get("sample_series_url") or "").strip()
        if not sample:
            by_id[sid] = {
                "check_status": "partial",
                "checked_at": now_iso(),
                "chapter_num": None,
                "label": None,
                "error": "no sample_series_url configured",
                "parser_version": None,
                "error_flags": "",
            }
            rows.append((sid, "partial", None, "no sample_series_url configured"))
            continue

        label, num, latest_url, err, info = app_module.scrape_latest_update(sample)
        checked = now_iso()
        pv = (info or {}).get("parser_version")
        flags = ",".join((info or {}).get("error_flags") or [])

        if err:
            status = "broken"
            by_id[sid] = {
                "check_status": status,
                "checked_at": checked,
                "chapter_num": num,
                "label": label,
                "error": err,
                "parser_version": pv,
                "error_flags": flags,
            }
            rows.append((sid, status, str(num) if num is not None else None, err))
        elif num is None:
            status = "partial"
            by_id[sid] = {
                "check_status": status,
                "checked_at": checked,
                "chapter_num": None,
                "label": label,
                "error": "scrape ok but no chapter number",
                "parser_version": pv,
                "error_flags": flags,
            }
            rows.append((sid, status, None, "no chapter number"))
        else:
            status = "working"
            by_id[sid] = {
                "check_status": status,
                "checked_at": checked,
                "chapter_num": num,
                "label": label,
                "chapter_url": latest_url,
                "error": None,
                "parser_version": pv,
                "error_flags": flags,
            }
            rows.append((sid, status, str(num), None))

    payload = {"updated_at": now_iso(), "by_id": by_id}
    out_path = source_registry.write_health(payload)
    if print_summary:
        print(f"Wrote {out_path}\n")
        for sid, status, num, err in rows:
            line = f"{sid:22} {status:10}"
            if num:
                line += f" latest={num}"
            if err:
                line += f" :: {err}"
            print(line)
    return {"path": str(out_path), "rows": rows, "updated_at": payload["updated_at"]}

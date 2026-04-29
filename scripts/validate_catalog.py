#!/usr/bin/env python3
"""Validate sources/catalog.json: every entry has domains and sample_series_url (http).

Exit 1 if any rule fails so CI can block merges with empty samples.

Usage (from repo root):
  python scripts/validate_catalog.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validate_payload(payload: dict) -> list[str]:
    errors: list[str] = []
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        errors.append('"sources" must be a list')
        return errors
    for i, raw in enumerate(sources):
        if not isinstance(raw, dict):
            errors.append(f"sources[{i}] must be an object")
            continue
        sid = (raw.get("id") or "").strip() or f"#{i}"
        domains = raw.get("domains")
        if not domains or not isinstance(domains, list) or not str(domains[0]).strip():
            errors.append(f'{sid}: missing "domains"')
        sample = (raw.get("sample_series_url") or "").strip()
        if not sample:
            errors.append(f"{sid}: sample_series_url is empty")
            continue
        if not sample.startswith(("http://", "https://")):
            errors.append(f"{sid}: sample_series_url must be an http(s) URL")
            continue
        try:
            pu = urlparse(sample)
            if not pu.netloc:
                raise ValueError("no host")
        except Exception:
            errors.append(f"{sid}: sample_series_url is not parseable")
            continue
        if not re.match(r"^https?://", sample):
            errors.append(f"{sid}: only http/https supported")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate sources/catalog.json structure and samples.")
    parser.add_argument(
        "--path",
        type=Path,
        default=ROOT / "sources" / "catalog.json",
        help="Path to catalog JSON",
    )
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1

    errs = validate_payload(payload)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"{len(errs)} error(s).", file=sys.stderr)
        return 1

    sources = payload.get("sources") or []
    print(f"OK: {len(sources)} source(s) validated at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

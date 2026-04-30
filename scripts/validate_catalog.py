#!/usr/bin/env python3
"""Validate sources data files.

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


def validate_manifest_payload(payload: list) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, list):
        return ['manifest payload must be a list']
    for i, ext in enumerate(payload):
        if not isinstance(ext, dict):
            errors.append(f"manifest[{i}] must be an object")
            continue
        ext_name = (ext.get("name") or ext.get("extension") or f"#{i}").strip()
        srcs = ext.get("sources")
        if not isinstance(srcs, list):
            errors.append(f"{ext_name}: sources must be a list")
            continue
        for j, src in enumerate(srcs):
            if not isinstance(src, dict):
                errors.append(f"{ext_name}: sources[{j}] must be an object")
                continue
            base = (src.get("baseUrl") or "").strip()
            if not base:
                # Some connector/local extensions intentionally omit a base URL.
                continue
            if not base.startswith(("http://", "https://")):
                errors.append(f"{ext_name}: sources[{j}] baseUrl must be an http(s) URL")
                continue
            try:
                pu = urlparse(base)
                if not pu.netloc:
                    raise ValueError("no host")
            except Exception:
                errors.append(f"{ext_name}: sources[{j}] baseUrl is not parseable")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate sources catalog/manifest structure.")
    parser.add_argument(
        "--path",
        type=Path,
        default=ROOT / "sources" / "sources.manifest.json",
        help="Path to sources data JSON",
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

    if isinstance(payload, list):
        errs = validate_manifest_payload(payload)
    else:
        errs = validate_payload(payload)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        print(f"{len(errs)} error(s).", file=sys.stderr)
        return 1

    if isinstance(payload, list):
        total = 0
        for ext in payload:
            if isinstance(ext, dict) and isinstance(ext.get("sources"), list):
                total += len(ext.get("sources"))
        print(f"OK: manifest validated at {path} ({len(payload)} extension records, {total} sources)")
    else:
        sources = payload.get("sources") or []
        print(f"OK: {len(sources)} source(s) validated at {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

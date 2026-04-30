from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_TOPLEVEL_FIELDS = (
    "extension",
    "package",
    "language",
    "version",
    "nsfw",
    "sources",
)

ALLOWED_SOURCE_FIELDS = ("name", "lang", "id", "baseUrl")

BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def _is_safe_public_http_url(raw: str) -> bool:
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host in BLOCKED_HOSTS:
        return False
    return True


def _clean_source(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    if bool(row.get("nsfw", False)):
        return None
    out = {k: row.get(k) for k in ALLOWED_SOURCE_FIELDS if k in row}
    base = str(out.get("baseUrl") or "").strip()
    if not _is_safe_public_http_url(base):
        return None
    out["baseUrl"] = base
    return out


def _clean_extension(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    if bool(row.get("nsfw", False)):
        return None
    srcs = row.get("sources")
    if not isinstance(srcs, list):
        return None
    cleaned_sources = []
    for src in srcs:
        cleaned = _clean_source(src)
        if cleaned:
            cleaned_sources.append(cleaned)
    if not cleaned_sources:
        return None
    out = {k: row.get(k) for k in ALLOWED_TOPLEVEL_FIELDS if k in row}
    out["nsfw"] = False
    out["sources"] = cleaned_sources
    return out


def build_manifest(input_path: Path, output_path: Path) -> tuple[int, int]:
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("Input manifest must be a JSON array")

    cleaned = []
    for ext in payload:
        row = _clean_extension(ext)
        if row:
            cleaned.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return len(payload), len(cleaned)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build filtered safe sources manifest for repository use.")
    parser.add_argument("--input", required=True, help="Raw upstream manifest JSON path")
    parser.add_argument("--output", default="sources/sources.manifest.json", help="Filtered manifest output path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if input_path.resolve() == output_path.resolve():
        print(
            "Warning: input and output paths are the same. "
            "Use a local raw upstream file (for example sources/sources.manifest.full.json) as input."
        )
    before, after = build_manifest(input_path, output_path)
    print(f"Safe manifest built: {after}/{before} extensions kept -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

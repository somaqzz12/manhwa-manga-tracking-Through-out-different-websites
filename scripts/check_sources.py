#!/usr/bin/env python3
"""Probe each catalog source (sample URL) and write sources/_health.json.

Run from repo root:
  python scripts/check_sources.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe each configured source sample URL and write sources/_health.json."
    )
    parser.parse_args(argv)

    from services import source_health_job  # noqa: E402

    source_health_job.run_and_write_health(print_summary=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

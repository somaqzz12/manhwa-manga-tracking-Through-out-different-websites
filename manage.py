#!/usr/bin/env python3
"""Operational CLI (catalog seeding, etc.)."""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="manage.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seed = sub.add_parser("seed_catalog", help="Seed global series catalog from API metadata providers")
    seed.add_argument("--source", choices=["mangadex", "anilist"], required=True)
    seed.add_argument("--limit", type=int, default=1000, help="Max series to ingest")
    seed.add_argument("--offset", type=int, default=0, help="MangaDex API offset")
    seed.add_argument("--page", type=int, default=1, help="AniList start page (1-based)")

    args = parser.parse_args()
    if args.cmd != "seed_catalog":
        return 1

    import db

    path = os.getenv("TRACKER_DB") or db.DB_PATH
    db.set_db_path(path)
    db.init_db()

    with db.get_conn() as conn:
        if args.source == "mangadex":
            from services.global_catalog.providers import mangadex_seed

            n = mangadex_seed.seed_mangadex(conn, limit=args.limit, offset_start=args.offset, log=print)
        else:
            from services.global_catalog.providers import anilist_seed

            n = anilist_seed.seed_anilist(conn, limit=args.limit, page_start=args.page, log=print)

    print(f"Done. Ingested {n} series (database: {path}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run a scrape from the command line.

  python -m scripts.run_ingestion                  # every active site
  python -m scripts.run_ingestion --site DPE       # one site, by name
  python -m scripts.run_ingestion --pages 1        # first page only
  python -m scripts.run_ingestion --quiet          # totals only

This is what a scheduler should call. Running it here rather than through the
API keeps a long scrape out of an HTTP request.
"""

import argparse
import asyncio
import logging
import sys

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.site import Site
from app.services.ingestion_service import run_ingestion


async def resolve_site_ids(names: list[str]) -> list[int]:
    async with AsyncSessionLocal() as db:
        ids = []
        for name in names:
            stmt = select(Site.id).where(func.lower(Site.name) == name.strip().lower())
            site_id = (await db.execute(stmt)).scalar_one_or_none()
            if site_id is None:
                print(f"No site named {name!r}. Check the Sites list.")
                return []
            ids.append(site_id)
        return ids


async def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape tender notices.")
    parser.add_argument("--site", action="append", default=[],
                        help="Site name; repeat for several. Default: all active sites.")
    parser.add_argument("--pages", type=int, default=None,
                        help="Maximum pages per site (default from settings).")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="How many sites to scrape at once.")
    parser.add_argument("--quiet", action="store_true", help="Totals only.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    site_ids = None
    if args.site:
        site_ids = await resolve_site_ids(args.site)
        if not site_ids:
            return 1

    run = await run_ingestion(
        site_ids=site_ids, max_pages=args.pages, concurrency=args.concurrency
    )
    summary = run.as_dict()
    totals = summary["totals"]

    if not args.quiet:
        print(f"\n{'SITE':<18} {'PAGES':>5} {'FOUND':>6} {'NEW':>5} {'DUP':>5} {'OLD':>5} {'UNCLS':>6}")
        print("-" * 56)
        for site in summary["sites"]:
            print(f"{site['name'][:18]:<18} {site['pages_fetched']:>5} {site['notices_found']:>6} "
                  f"{site['inserted']:>5} {site['duplicates']:>5} {site['too_old']:>5} "
                  f"{site['unclassified']:>6}")
            if site["error"]:
                print(f"                   error: {site['error'][:70]}")

    print(f"\nFinished in {summary['duration_seconds']}s")
    print(f"  sites:        {totals['sites_attempted']} attempted, {totals['sites_failed']} failed")
    print(f"  notices:      {totals['notices_found']} found")
    print(f"  stored:       {totals['inserted']} new, {totals['duplicates']} already known")
    print(f"  skipped:      {totals['too_old']} older than the cutoff")
    print(f"  unclassified: {totals['unclassified']} stored without a category")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

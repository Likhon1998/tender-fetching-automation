"""Show what each column of a site's table actually contains.

Several notice boards list a publish date and a submission deadline in
separate columns, but only one of them is configured. Run this against a site
to see its columns, then set `submission=<index>` for it in
app/ingestion/parsers.py.

  python -m scripts.inspect_columns --site BangladeshBank
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.firecrawl import FirecrawlClient
from app.ingestion.html_utils import extract_cells, pick_best_table, strip_tags
from app.ingestion.parsers import POSITIONAL_COLUMNS, SITE_STRATEGIES
from app.models.site import Site


async def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a site's table columns.")
    parser.add_argument("--site", required=True, help="Site name, e.g. BangladeshBank")
    parser.add_argument("--rows", type=int, default=4, help="How many rows to show.")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        stmt = select(Site).where(func.lower(Site.name) == args.site.strip().lower())
        site = (await db.execute(stmt)).scalar_one_or_none()

    if site is None:
        print(f"No site named {args.site!r}.")
        return 1

    strategy = site.strategy or SITE_STRATEGIES.get(site.name)
    if strategy != "positional":
        print(f"{site.name} uses the {strategy!r} strategy, which has no columns.")
        return 1

    config = POSITIONAL_COLUMNS.get(site.name)
    print(f"{site.name}  {site.url}")
    print(f"configured: {config}\n")

    client = FirecrawlClient(settings.FIRECRAWL_API_KEY, base_url=settings.FIRECRAWL_URL)
    try:
        html = await client.scrape(site.url)
    finally:
        await client.aclose()

    rows = pick_best_table(html, config.min_cols if config else 2)
    if not rows:
        print("No table matched. The page markup may have changed.")
        return 1

    for row in rows[: args.rows]:
        cells = [strip_tags(c)[:44] for c in extract_cells(row)]
        for index, text in enumerate(cells):
            marks = []
            if config:
                if index == config.title: marks.append("title")
                if index == config.date: marks.append("date")
                if index == config.submission: marks.append("submission")
                if index == config.link: marks.append("link")
            label = f"  <- {', '.join(marks)}" if marks else ""
            print(f"  [{index}] {text!r}{label}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

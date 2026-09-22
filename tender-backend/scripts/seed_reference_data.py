"""Seed the predefined categories and sites from the specification.

Run with:  python -m scripts.seed_reference_data

Idempotent: existing rows are matched by name and left alone, so running it
again will not create duplicates or overwrite admin edits. Pass --update to
refresh descriptions, keywords and URLs from the specification instead.
"""

import asyncio
import sys

from sqlalchemy import func, select

from app.data.reference_data import CATEGORIES, SITES
from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.site import Site


async def main(update_existing: bool = False) -> int:
    created = {"categories": 0, "sites": 0}
    updated = {"categories": 0, "sites": 0}

    async with AsyncSessionLocal() as db:
        for spec in CATEGORIES:
            stmt = select(Category).where(
                func.lower(Category.name) == spec["name"].lower()
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                db.add(Category(**spec))
                created["categories"] += 1
            elif update_existing:
                row.description = spec["description"]
                row.keywords = spec["keywords"]
                updated["categories"] += 1

        for spec in SITES:
            stmt = select(Site).where(func.lower(Site.name) == spec["name"].lower())
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                db.add(Site(**spec))
                created["sites"] += 1
            elif update_existing:
                row.url = spec["url"]
                row.strategy = spec.get("strategy")
                updated["sites"] += 1

        await db.commit()

    print(
        f"Categories: {created['categories']} created, "
        f"{updated['categories']} updated"
    )
    print(f"Sites:      {created['sites']} created, {updated['sites']} updated")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--update" in sys.argv)))

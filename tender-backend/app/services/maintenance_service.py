"""Destructive maintenance actions.

These exist so an admin can reset the tool between demos or after a change to
the parsers, without dropping to the database by hand.

Two levels, deliberately separate:

  * ``lists``      removes every saved list. The tenders themselves stay, so
                   nothing has to be scraped again and they remain visible
                   under "Everything scraped".
  * ``everything`` removes the saved lists and every stored tender, so the
                   next search starts from nothing.

Neither touches users, sites or categories. Wiping the site list or the
keyword lists would mean re-seeding to get the tool working again, which is a
much bigger step than clearing collected data and should not sit behind the
same button.
"""

import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search import Search, search_tenders
from app.models.tender import Tender

logger = logging.getLogger(__name__)

LISTS = "lists"
EVERYTHING = "everything"
SCOPES = (LISTS, EVERYTHING)


async def preview(db: AsyncSession) -> dict:
    """What clearing would remove, so the warning can be specific."""
    lists = (await db.execute(select(func.count()).select_from(Search))).scalar_one()
    tenders = (await db.execute(select(func.count()).select_from(Tender))).scalar_one()
    saved = (
        await db.execute(select(func.count()).select_from(search_tenders))
    ).scalar_one()
    return {"saved_lists": lists, "saved_tenders": saved, "stored_tenders": tenders}


async def clear(db: AsyncSession, scope: str) -> dict:
    """Delete collected data. Returns what was removed."""
    if scope not in SCOPES:
        raise ValueError(f"Unknown scope {scope!r}")

    before = await preview(db)

    # Links first: the foreign keys cascade, but deleting them explicitly
    # keeps the reported counts honest.
    await db.execute(delete(search_tenders))
    await db.execute(delete(Search))

    removed_tenders = 0
    if scope == EVERYTHING:
        await db.execute(delete(Tender))
        removed_tenders = before["stored_tenders"]

    await db.commit()

    result = {
        "scope": scope,
        "lists_removed": before["saved_lists"],
        "tenders_removed": removed_tenders,
        "tenders_kept": 0 if scope == EVERYTHING else before["stored_tenders"],
    }
    logger.warning(
        "Cleared %s: %s list(s), %s tender(s) removed",
        scope, result["lists_removed"], result["tenders_removed"],
    )
    return result

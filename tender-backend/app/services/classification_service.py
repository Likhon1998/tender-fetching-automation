"""Loads categories from the database and applies the classifier."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.classifier import Classification, Classifier
from app.models.category import Category
from app.models.tender import Tender


async def build_classifier(db: AsyncSession) -> Classifier:
    """Construct a classifier from the current categories and keywords.

    Built fresh each time rather than cached, so an admin editing keywords
    through the API takes effect on the next run without a restart.
    """
    stmt = select(Category.id, Category.name, Category.keywords).order_by(Category.id)
    rows = (await db.execute(stmt)).all()
    return Classifier([(r.id, r.name, r.keywords or []) for r in rows])


def apply(tender: Tender, result: Classification | None) -> None:
    """Write a classification onto a tender, or clear it if nothing matched."""
    if result is None:
        tender.category_id = None
        tender.category = None
        tender.confidence = None
    else:
        tender.category_id = result.category_id
        tender.category = result.category_name
        tender.confidence = result.confidence


async def reclassify_all(db: AsyncSession) -> dict:
    """Re-run classification over every stored tender.

    This is the payoff for storing notices the classifier rejected: after
    editing keywords, previously unmatched tenders can be picked up without
    re-scraping anything.
    """
    classifier = await build_classifier(db)
    tenders = list((await db.execute(select(Tender))).scalars().all())

    changed = 0
    newly_classified = 0
    newly_unclassified = 0

    for tender in tenders:
        before = tender.category_id
        result = classifier.classify(tender.title)
        after = result.category_id if result else None

        if before != after:
            changed += 1
            if before is None and after is not None:
                newly_classified += 1
            elif before is not None and after is None:
                newly_unclassified += 1

        apply(tender, result)

    await db.commit()

    classified = sum(1 for t in tenders if t.category_id is not None)
    return {
        "examined": len(tenders),
        "classified": classified,
        "unclassified": len(tenders) - classified,
        "changed": changed,
        "newly_classified": newly_classified,
        "newly_unclassified": newly_unclassified,
        "keywords_in_use": classifier.keyword_count,
    }
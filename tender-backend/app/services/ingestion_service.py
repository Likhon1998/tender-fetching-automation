"""The scraping run: fetch, parse, classify, store.

For each active site this fetches up to a fixed number of pages through
Firecrawl, parses each page with that site's strategy, classifies every notice
against the keyword lists, and stores the results.

Two things shape the design:

  * One site's failure must not stop the run. A portal that changes its markup
    or times out records an error against itself and the rest continue.
  * Every notice is stored, including ones the classifier could not place.
    Filtering happens when reading, so the relevance rules and date cutoff can
    change later without scraping all 38 sites again.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.ingestion.classifier import Classifier
from app.ingestion.dates import find_deadline, is_within_cutoff, normalise_date
from app.ingestion.firecrawl import FirecrawlClient, FirecrawlError
from app.ingestion.pagination import find_next_page
from app.ingestion.parsers import UnknownStrategy, parse_page
from app.models.site import Site
from app.models.tender import Tender
from app.services.classification_service import build_classifier

logger = logging.getLogger(__name__)


@dataclass
class SiteResult:
    site_id: int
    name: str
    pages_fetched: int = 0
    notices_found: int = 0
    inserted: int = 0
    duplicates: int = 0
    too_old: int = 0
    unclassified: int = 0
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "name": self.name,
            "pages_fetched": self.pages_fetched,
            "notices_found": self.notices_found,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "too_old": self.too_old,
            "unclassified": self.unclassified,
            "error": self.error,
        }


@dataclass
class RunResult:
    started_at: datetime
    finished_at: datetime | None = None
    sites: list[SiteResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        totals = {
            "sites_attempted": len(self.sites),
            "sites_failed": sum(1 for s in self.sites if s.error),
            "pages_fetched": sum(s.pages_fetched for s in self.sites),
            "notices_found": sum(s.notices_found for s in self.sites),
            "inserted": sum(s.inserted for s in self.sites),
            "duplicates": sum(s.duplicates for s in self.sites),
            "too_old": sum(s.too_old for s in self.sites),
            "unclassified": sum(s.unclassified for s in self.sites),
        }
        duration = None
        if self.finished_at:
            duration = round((self.finished_at - self.started_at).total_seconds(), 1)
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": duration,
            "totals": totals,
            "sites": [s.as_dict() for s in self.sites],
        }


async def _store_notice(
    db: AsyncSession,
    notice,
    site_id: int,
    site_name: str,
    site_url: str,
    classifier: Classifier,
    result: SiteResult,
    cutoff_year: int,
) -> None:
    """Classify one parsed notice and insert it, skipping duplicates."""
    if not is_within_cutoff(notice.date_raw, cutoff_year):
        result.too_old += 1
        return

    # The specification treats the title as the unique key: the same notice
    # published on two sites is stored once.
    exists = await db.execute(
        select(Tender.id).where(Tender.title == notice.title).limit(1)
    )
    if exists.scalar_one_or_none() is not None:
        result.duplicates += 1
        return

    parsed_date, raw = normalise_date(notice.date_raw)

    # Work out the deadline, in order of reliability: a column of its own,
    # then the title text, then the main date where that is itself a deadline.
    deadline, deadline_raw = None, ""
    if notice.submission_raw:
        deadline, deadline_raw = normalise_date(notice.submission_raw)
    if deadline is None:
        deadline, deadline_raw = find_deadline(notice.title)
    if deadline is None and notice.date_type == "submission":
        deadline, deadline_raw = parsed_date, raw

    classification = classifier.classify(notice.title)
    if classification is None:
        result.unclassified += 1

    tender = Tender(
        title=notice.title,
        date=parsed_date,
        date_raw=raw,
        date_type=notice.date_type,
        submission_date=deadline,
        submission_date_raw=deadline_raw or None,
        pdf_link=notice.pdf_link or None,
        site_id=site_id,
        source_name=site_name,
        source_url=site_url,
        category_id=classification.category_id if classification else None,
        category=classification.category_name if classification else None,
        confidence=classification.confidence if classification else None,
    )
    db.add(tender)

    try:
        await db.commit()
        result.inserted += 1
    except IntegrityError:
        # Another site in this same run inserted the same title first.
        await db.rollback()
        result.duplicates += 1


async def _process_site(
    site_id: int,
    client: FirecrawlClient,
    classifier: Classifier,
    max_pages: int,
    cutoff_year: int,
) -> SiteResult:
    """Scrape one site end to end, using its own database session."""
    async with AsyncSessionLocal() as db:
        site = await db.get(Site, site_id)
        if site is None:
            return SiteResult(site_id=site_id, name="?", error="Site no longer exists")

        # Copy what we need out of the ORM object up front. Every insert
        # commits, and a rollback on a duplicate expires loaded instances,
        # which would turn a later `site.url` into a surprise database read
        # in the middle of the loop.
        name, base_url, strategy = site.name, site.url, site.strategy

        result = SiteResult(site_id=site_id, name=name)
        url = base_url
        page = 1
        error: str | None = None

        try:
            while page <= max_pages:
                html = await client.scrape(url)
                result.pages_fetched += 1

                notices = parse_page(
                    html, site_name=name, source_url=url, strategy=strategy
                )
                result.notices_found += len(notices)

                for notice in notices:
                    await _store_notice(
                        db, notice, site_id, name, base_url,
                        classifier, result, cutoff_year,
                    )

                nxt = find_next_page(
                    html, current_page=page, base_url=base_url, max_pages=max_pages
                )
                if nxt is None:
                    break
                page, url = nxt

        except (FirecrawlError, UnknownStrategy) as exc:
            error = str(exc)
            logger.warning("%s: %s", name, exc)
        except Exception as exc:  # noqa: BLE001 - one site must not kill the run
            error = f"{type(exc).__name__}: {exc}"
            logger.exception("%s: unexpected failure", name)

        result.error = error

        # Re-read the row rather than reusing the instance from earlier, which
        # may have been expired by a rollback.
        site = await db.get(Site, site_id)
        if site is not None:
            site.last_scraped_at = datetime.now(timezone.utc)
            site.last_scrape_error = error[:500] if error else None
            await db.commit()

    return result


async def run_ingestion(
    *,
    site_ids: list[int] | None = None,
    max_pages: int | None = None,
    concurrency: int = 3,
    on_site_done=None,
) -> RunResult:
    """Run a full scrape.

    `site_ids` limits the run to specific sites, which is useful when testing
    a single portal rather than waiting for all 38.

    `on_site_done(name, done, total)` is awaited after each site finishes, so
    a caller can report progress while a long run is in flight.
    """
    max_pages = max_pages or settings.MAX_PAGES_PER_SITE
    cutoff_year = settings.TENDER_CUTOFF_YEAR
    run = RunResult(started_at=datetime.now(timezone.utc))

    async with AsyncSessionLocal() as db:
        stmt = select(Site.id).where(Site.active.is_(True)).order_by(Site.name)
        if site_ids:
            stmt = stmt.where(Site.id.in_(site_ids))
        targets = list((await db.execute(stmt)).scalars().all())
        classifier = await build_classifier(db)

    if not targets:
        run.finished_at = datetime.now(timezone.utc)
        return run

    logger.info("Starting ingestion for %s site(s)", len(targets))

    client = FirecrawlClient(
        settings.FIRECRAWL_API_KEY,
        base_url=settings.FIRECRAWL_URL,
        wait_for_ms=settings.FIRECRAWL_WAIT_FOR_MS,
        scrape_timeout_ms=settings.FIRECRAWL_TIMEOUT_MS,
        max_retries=settings.FIRECRAWL_MAX_RETRIES,
        max_concurrent=settings.FIRECRAWL_MAX_CONCURRENT,
        delay_between_s=settings.FIRECRAWL_DELAY_SECONDS,
    )

    limiter = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(targets)

    async def worker(site_id: int) -> SiteResult:
        nonlocal completed
        async with limiter:
            result = await _process_site(
                site_id, client, classifier, max_pages, cutoff_year
            )
        completed += 1
        if on_site_done is not None:
            try:
                await on_site_done(result.name, completed, total)
            except Exception:  # noqa: BLE001 - progress must never break the run
                logger.exception("Progress callback failed")
        return result

    try:
        run.sites = list(await asyncio.gather(*(worker(sid) for sid in targets)))
    finally:
        await client.aclose()

    run.finished_at = datetime.now(timezone.utc)
    totals = run.as_dict()["totals"]
    logger.info(
        "Ingestion finished: %s inserted, %s duplicates, %s failed sites",
        totals["inserted"], totals["duplicates"], totals["sites_failed"],
    )
    return run

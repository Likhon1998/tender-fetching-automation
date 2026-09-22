"""End-to-end test of the scraping run: fetch, parse, classify, store.

Firecrawl is replaced with a fake that serves canned HTML, so this makes no
network calls and costs no credits.

Run with:  PYTHONPATH=. python tests/ingestion_test.py
"""

import asyncio
import os
from pathlib import Path

DB = Path(__file__).parent / "ingestion_test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"
os.environ["FIRECRAWL_API_KEY"] = "fc-test-key"

from sqlalchemy import func, select  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.ingestion.firecrawl import FirecrawlError  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tender import Tender  # noqa: E402
from app.services import ingestion_service  # noqa: E402

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


PAD = "<nav>menu</nav><header><h1>Notices</h1><p>Published tenders and circulars.</p></header>"


def table_page(rows: str) -> str:
    return f"""<html><body>{PAD}<table>
<tr><th>Date</th><th>Title</th><th>Link</th></tr>{rows}
</table>
<ul class="pagination"><a href="?page=1">1</a><a href="?page=2">2</a></ul>
</body></html>"""


def last_page(rows: str) -> str:
    return f"""<html><body>{PAD}<table>
<tr><th>Date</th><th>Title</th><th>Link</th></tr>{rows}
</table></body></html>"""


def row(date, title, link):
    return f'<tr><td>{date}</td><td>{title}</td><td><a href="{link}">PDF</a></td></tr>'


# What the fake Firecrawl serves for each URL.
PAGES = {
    "https://alpha.test/tenders": table_page(
        row("15-Jun-2026", "Procurement of Firewall and Network Security Appliances", "/a1.pdf")
        + row("20-Jun-2026", "Supply of Laptop Computers for Branch Offices", "/a2.pdf")
        + row("01-Mar-2019", "Very old notice about network switches", "/a3.pdf")
    ),
    "https://alpha.test/tenders?page=2": last_page(
        row("25-Jun-2026", "Tender for Cyber Security Audit and VAPT Services", "/a4.pdf")
        + row("26-Jun-2026", "Notice for disposal of old office furniture", "/a5.pdf")
    ),
    "https://beta.test/notices": last_page(
        row("10-Jul-2026", "Request for Proposal: Data Center Migration", "/b1.pdf")
        # Same title as a notice on alpha: must be stored only once.
        + row("11-Jul-2026", "Supply of Laptop Computers for Branch Offices", "/b2.pdf")
    ),
}


class FakeFirecrawl:
    """Stands in for FirecrawlClient. Serves canned pages, fails on demand."""

    def __init__(self, *_, **__):
        self.calls = []

    async def scrape(self, url: str) -> str:
        self.calls.append(url)
        if "broken.test" in url:
            raise FirecrawlError(f"Failed to scrape {url}: simulated outage")
        if url not in PAGES:
            raise FirecrawlError(f"No canned page for {url}")
        return PAGES[url]

    async def aclose(self):
        pass


async def setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        db.add_all([
            Category(name="Network Security",
                     keywords=["firewall", "network security", "network switch"]),
            Category(name="Cyber Security", keywords=["cyber security", "vapt", "audit"]),
            Category(name="IT Infrastructures", keywords=["laptop", "computer", "printer"]),
            Category(name="Data Center Solutions",
                     keywords=["data center", "data centre", "migration"]),
        ])
        db.add_all([
            Site(name="Alpha", url="https://alpha.test/tenders", strategy="positional"),
            Site(name="Beta", url="https://beta.test/notices", strategy="positional"),
            Site(name="Broken", url="https://broken.test/x", strategy="positional"),
            Site(name="Paused", url="https://paused.test/x", strategy="positional",
                 active=False),
        ])
        await db.commit()


async def main():
    await setup()

    # Alpha and Beta both use a table with date, title, link in columns 0, 1, 2.
    from app.ingestion.parsers import POSITIONAL_COLUMNS, PositionalColumns
    for name in ("Alpha", "Beta", "Broken"):
        POSITIONAL_COLUMNS[name] = PositionalColumns(title=1, link=2, date=0, min_cols=3)

    fake = FakeFirecrawl()
    ingestion_service.FirecrawlClient = lambda *a, **k: fake

    print("=== full run ===")
    run = await ingestion_service.run_ingestion(max_pages=5, concurrency=2)
    summary = run.as_dict()
    totals = summary["totals"]
    for site in summary["sites"]:
        print(f"  {site['name']:8} pages={site['pages_fetched']} found={site['notices_found']} "
              f"new={site['inserted']} dup={site['duplicates']} old={site['too_old']} "
              f"uncls={site['unclassified']}"
              + (f"  error={site['error'][:40]}" if site["error"] else ""))

    check("paused site not scraped", any(s["name"] == "Paused" for s in summary["sites"]), False)
    check("three sites attempted", totals["sites_attempted"], 3)
    check("one site failed", totals["sites_failed"], 1)
    check("alpha followed pagination",
          next(s["pages_fetched"] for s in summary["sites"] if s["name"] == "Alpha"), 2)
    check("pre-cutoff notice skipped", totals["too_old"], 1)
    check("duplicate title stored once", totals["duplicates"], 1)
    check("unclassified notice still stored", totals["unclassified"], 1)
    check("five notices inserted", totals["inserted"], 5)

    async with AsyncSessionLocal() as db:
        stored = (await db.execute(select(Tender).order_by(Tender.title))).scalars().all()
        print("\n  stored tenders:")
        for t in stored:
            print(f"    {t.title[:52]:54} {t.source_name:6} {t.date} {t.category or '-'}")

        check("row count matches", len(stored), 5)
        check("old notice absent",
              any("Very old" in t.title for t in stored), False)

        # The same notice appears on both Alpha and Beta. It is stored once,
        # but sites are scraped concurrently, so which site's copy wins is
        # whichever committed first. Assert the dedup, not the winner.
        laptops = [t for t in stored if "Laptop" in t.title]
        check("duplicate stored only once", len(laptops), 1)
        check("attributed to one of the two sites",
              laptops[0].source_name in {"Alpha", "Beta"}, True)
        check("classified correctly", laptops[0].category, "IT Infrastructures")

        furniture = next(t for t in stored if "furniture" in t.title)
        check("irrelevant notice has no category", furniture.category, None)
        check("irrelevant notice has no confidence", furniture.confidence, None)

        firewall = next(t for t in stored if "Firewall" in t.title)
        check("date parsed to ISO", str(firewall.date), "2026-06-15")
        check("raw date preserved", firewall.date_raw, "15-Jun-2026")
        check("relative link made absolute", firewall.pdf_link, "https://alpha.test/a1.pdf")
        check("linked to its site", firewall.source_name, "Alpha")

        # Every site records when it ran; the broken one records why it failed.
        sites = {s.name: s for s in (await db.execute(select(Site))).scalars().all()}
        check("alpha timestamped", sites["Alpha"].last_scraped_at is not None, True)
        check("alpha has no error", sites["Alpha"].last_scrape_error, None)
        check("broken site recorded an error",
              "simulated outage" in (sites["Broken"].last_scrape_error or ""), True)
        check("broken site still timestamped", sites["Broken"].last_scraped_at is not None, True)
        check("paused site untouched", sites["Paused"].last_scraped_at, None)

    print("\n=== re-running finds nothing new ===")
    run2 = await ingestion_service.run_ingestion(max_pages=5, concurrency=2)
    t2 = run2.as_dict()["totals"]
    print(f"  inserted={t2['inserted']} duplicates={t2['duplicates']}")
    check("second run inserts nothing", t2["inserted"], 0)
    async with AsyncSessionLocal() as db:
        total = (await db.execute(select(func.count()).select_from(Tender))).scalar_one()
    check("still five tenders", total, 5)

    print("\n=== single site run ===")
    async with AsyncSessionLocal() as db:
        beta_id = (await db.execute(select(Site.id).where(Site.name == "Beta"))).scalar_one()
    run3 = await ingestion_service.run_ingestion(site_ids=[beta_id], max_pages=5)
    check("only one site attempted", run3.as_dict()["totals"]["sites_attempted"], 1)

    print("\n=== page limit is honoured ===")
    async with AsyncSessionLocal() as db:
        await db.execute(Tender.__table__.delete())
        await db.commit()
    run4 = await ingestion_service.run_ingestion(max_pages=1, concurrency=2)
    alpha = next(s for s in run4.as_dict()["sites"] if s["name"] == "Alpha")
    check("stopped after one page", alpha["pages_fetched"], 1)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL INGESTION CHECKS PASSED")


asyncio.run(main())

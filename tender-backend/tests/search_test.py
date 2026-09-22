"""End-to-end test of the search wizard: choose, scrape, review, save.

Firecrawl is faked, so no network calls and no credits.

Run with:  PYTHONPATH=. python tests/search_test.py
"""

import asyncio
import os
from pathlib import Path

DB = Path(__file__).parent / "search_test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"
os.environ["FIRECRAWL_API_KEY"] = "fc-test-key"

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.ingestion.firecrawl import FirecrawlError  # noqa: E402
from app.ingestion.parsers import POSITIONAL_COLUMNS, PositionalColumns  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.search import Search, search_tenders  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tender import Tender  # noqa: E402
from app.core.capabilities import (  # noqa: E402
    SAVE_LISTS,
    SEARCH_TENDERS,
    TRIAGE_TENDERS,
)
from app.models.user import User  # noqa: E402
from app.services import ingestion_service  # noqa: E402

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


PAD = "<nav>menu</nav><header><h1>Notices</h1><p>Tenders published here.</p></header>"


def page(rows):
    return (f"<html><body>{PAD}<table>"
            f"<tr><th>Date</th><th>Title</th><th>Link</th></tr>{rows}"
            "</table></body></html>")


def row(date, title, link):
    return f'<tr><td>{date}</td><td>{title}</td><td><a href="{link}">PDF</a></td></tr>'


PAGES = {
    "https://alpha.test/t": page(
        row("15-Jun-2026", "Procurement of Firewall and Network Security Appliances", "/a1.pdf")
        + row("16-Jun-2026", "Supply of Laptop Computers for Branch Offices", "/a2.pdf")
        + row("17-Jun-2026", "Notice for disposal of old office furniture", "/a3.pdf")
    ),
    "https://beta.test/t": page(
        row("10-Jul-2026", "Tender for Cyber Security Audit and VAPT Services", "/b1.pdf")
        + row("11-Jul-2026", "Auction of surplus vehicles", "/b2.pdf")
    ),
}


class FakeFirecrawl:
    def __init__(self, *_, **__):
        self.calls = []

    async def scrape(self, url):
        self.calls.append(url)
        if url not in PAGES:
            raise FirecrawlError(f"no canned page for {url}")
        return PAGES[url]

    async def aclose(self):
        pass


fake = FakeFirecrawl()


async def wait_for(search_id, client, headers, timeout=25):
    for _ in range(timeout * 10):
        body = (await client.get(f"/api/v1/searches/{search_id}", headers=headers)).json()
        if body["status"] in ("completed", "failed"):
            return body
        await asyncio.sleep(0.1)
    raise TimeoutError("search did not finish")


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        db.add(User(username="staff", full_name="Staff", email="s@x.com",
                    password_hash=hash_password("StaffPassword123"), capabilities=[SEARCH_TENDERS, SAVE_LISTS, TRIAGE_TENDERS]))
        netsec = Category(name="Network Security", keywords=["firewall"])
        cyber = Category(name="Cyber Security", keywords=["vapt", "cyber security"])
        # Long enough to satisfy the classifier's single-keyword threshold of
        # eight characters, which "laptop" alone would not meet.
        itinfra = Category(name="IT Infrastructures",
                           keywords=["laptop computer", "computer"])
        db.add_all([netsec, cyber, itinfra])
        alpha = Site(name="Alpha", url="https://alpha.test/t", strategy="positional")
        beta = Site(name="Beta", url="https://beta.test/t", strategy="positional")
        db.add_all([alpha, beta])
        await db.commit()
        for o in (netsec, cyber, itinfra, alpha, beta):
            await db.refresh(o)
        ids = {"alpha": alpha.id, "beta": beta.id,
               "netsec": netsec.id, "cyber": cyber.id, "itinfra": itinfra.id}

    for name in ("Alpha", "Beta"):
        POSITIONAL_COLUMNS[name] = PositionalColumns(title=1, link=2, date=0, min_cols=3)
    ingestion_service.FirecrawlClient = lambda *a, **k: fake

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/authenticate",
                         json={"identifier": "staff", "password": "StaffPassword123"})
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        print("=== validation ===")
        r = await c.post("/api/v1/searches", headers=headers,
                         json={"site_ids": [], "category_ids": [ids["netsec"]]})
        check("no sites is rejected", r.status_code, 422)
        r = await c.post("/api/v1/searches", headers=headers,
                         json={"site_ids": [ids["alpha"]], "category_ids": []})
        check("no categories is rejected", r.status_code, 400)
        r = await c.post("/api/v1/searches", headers=headers,
                         json={"site_ids": [9999], "category_ids": [ids["netsec"]]})
        check("unknown site is rejected", r.status_code, 404)
        r = await c.post("/api/v1/searches",
                         json={"site_ids": [ids["alpha"]], "category_ids": [ids["netsec"]]})
        check("needs a token", r.status_code, 401)

        print("\n=== the search scrapes when it runs ===")
        r = await c.post("/api/v1/searches", headers=headers, json={
            "site_ids": [ids["alpha"], ids["beta"]],
            "category_ids": [ids["netsec"], ids["itinfra"]],
        })
        check("accepted for background work", r.status_code, 202)
        first = r.json()
        check("starts pending", first["status"], "pending")
        check("not saved yet", first["saved"], False)

        done = await wait_for(first["id"], c, headers)
        check("finishes", done["status"], "completed")
        check("both sites scraped", done["sites_done"], 2)
        check("firecrawl was actually called", len(fake.calls) >= 2, True)

        print("\n=== results before saving ===")
        r = await c.get(f"/api/v1/searches/{first['id']}/tenders", headers=headers)
        results = r.json()
        for t in results["items"]:
            print(f"    {t['category']:<20} {t['title'][:46]}")
        check("shows the matching tenders", results["total"], 2)
        check("still not a saved list", results["search"]["saved"], False)
        check("nothing kept yet", results["search"]["tender_count"], 0)

        titles = [t["title"] for t in results["items"]]
        check("furniture excluded", any("furniture" in t for t in titles), False)
        check("unselected category excluded", any("Cyber" in t for t in titles), False)

        print("\n=== select all needs every id, not just this page ===")
        r = await c.get(f"/api/v1/searches/{first['id']}/tender-ids", headers=headers)
        all_ids = r.json()["tender_ids"]
        check("returns the whole result set", len(all_ids), 2)

        print("\n=== saving a subset ===")
        one = [results["items"][0]["id"]]
        r = await c.post(f"/api/v1/searches/{first['id']}/save",
                         headers=headers, json={"tender_ids": one})
        saved = r.json()
        check("saved", r.status_code, 200)
        check("marked as a list", saved["saved"], True)
        check("counted what was kept", saved["tender_count"], 1)

        r = await c.get(f"/api/v1/searches/{first['id']}/tenders", headers=headers)
        check("now shows only what was kept", r.json()["total"], 1)

        print("\n=== saving again replaces the selection ===")
        r = await c.post(f"/api/v1/searches/{first['id']}/save",
                         headers=headers, json={"tender_ids": all_ids})
        check("count updated", r.json()["tender_count"], 2)
        async with AsyncSessionLocal() as db:
            links = (await db.execute(
                select(func.count()).select_from(search_tenders)
                .where(search_tenders.c.search_id == first["id"]))).scalar_one()
        check("no duplicate links", links, 2)

        print("\n=== a tender from outside the search cannot be attached ===")
        async with AsyncSessionLocal() as db:
            stray = Tender(title="Unrelated notice from nowhere", source_name="Other")
            db.add(stray)
            await db.commit()
            await db.refresh(stray)
            stray_id = stray.id
        r = await c.post(f"/api/v1/searches/{first['id']}/save",
                         headers=headers, json={"tender_ids": all_ids + [stray_id]})
        check("stray id ignored", r.json()["tender_count"], 2)

        print("\n=== uncategorised option ===")
        r = await c.post("/api/v1/searches", headers=headers, json={
            "site_ids": [ids["alpha"], ids["beta"]],
            "category_ids": [], "include_uncategorised": True,
        })
        third = await wait_for(r.json()["id"], c, headers)
        r = await c.get(f"/api/v1/searches/{third['id']}/tenders", headers=headers)
        got = [t["title"] for t in r.json()["items"]]
        check("returns only unclassified notices", r.json()["total"], 2)
        check("includes the furniture notice", any("furniture" in t for t in got), True)

        print("\n=== saved lists ===")
        # The third search was never saved, so it must not appear.
        r = await c.get("/api/v1/searches", headers=headers)
        check("only saved lists are listed", len(r.json()), 1)
        check("records who saved it", r.json()[0]["created_by_username"], "staff")

        r = await c.post(f"/api/v1/searches/{third['id']}/save",
                         headers=headers, json={"tender_ids": []})
        check("saving nothing is allowed", r.json()["tender_count"], 0)
        r = await c.get("/api/v1/searches", headers=headers)
        check("now two lists", len(r.json()), 2)

        print("\n=== you cannot save before the scrape finishes ===")
        r = await c.post("/api/v1/searches", headers=headers, json={
            "site_ids": [ids["alpha"]], "category_ids": [ids["netsec"]],
        })
        pending_id = r.json()["id"]
        await wait_for(pending_id, c, headers)
        # Force it back to running: the fake scraper finishes too quickly to
        # catch mid-flight, but the guard still needs testing.
        async with AsyncSessionLocal() as db:
            row = await db.get(Search, pending_id)
            row.status = "running"
            await db.commit()
        r = await c.post(f"/api/v1/searches/{pending_id}/save",
                         headers=headers, json={"tender_ids": []})
        check("rejected while running", r.status_code, 409)

        print("\n=== result filters ===")
        r = await c.get(f"/api/v1/searches/{first['id']}/tenders?search=firewall",
                        headers=headers)
        check("text search within a list", r.json()["total"], 1)
        tid = r.json()["items"][0]["id"]
        await c.patch(f"/api/v1/tenders/{tid}", headers=headers,
                      json={"status": "not_interested"})
        r = await c.get(f"/api/v1/searches/{first['id']}/tenders", headers=headers)
        check("dismissed leaves the default view", r.json()["total"], 1)
        r = await c.get(f"/api/v1/searches/{first['id']}/tenders?status=all",
                        headers=headers)
        check("but stays in the list", r.json()["total"], 2)

        print("\n=== deleting a list ===")
        r = await c.delete(f"/api/v1/searches/{third['id']}", headers=headers)
        check("deleted", r.status_code, 204)
        r = await c.get(f"/api/v1/searches/{third['id']}", headers=headers)
        check("gone", r.status_code, 404)
        async with AsyncSessionLocal() as db:
            left = (await db.execute(select(func.count()).select_from(Tender))).scalar_one()
        check("its tenders survive", left, 6)

        r = await c.get("/api/v1/searches/99999/tenders", headers=headers)
        check("missing search is a 404", r.status_code, 404)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL SEARCH CHECKS PASSED")


asyncio.run(main())

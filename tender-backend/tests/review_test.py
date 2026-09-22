"""Tests for the review inbox: keeping tenders a scheduled scrape brought in.

Scheduled runs store tenders nobody asked for. This covers seeing those, and
turning a chosen few into a saved list.

Run with:  PYTHONPATH=. python tests/review_test.py
"""

import asyncio
import os
from datetime import date
from pathlib import Path

DB = Path(__file__).parent / "review_test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.core.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    SEARCH_TENDERS,
    TRIAGE_TENDERS,
)
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.search import Search, search_tenders  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tender import Tender  # noqa: E402
from app.models.user import User  # noqa: E402

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        db.add(User(username="admin", full_name="Admin", email="a@x.com",
                    password_hash=hash_password("AdminPassword123"),
                    capabilities=list(ALL_CAPABILITIES)))
        # Can look, cannot keep.
        db.add(User(username="viewer", full_name="Viewer", email="v@x.com",
                    password_hash=hash_password("ViewerPassword1"),
                    capabilities=[SEARCH_TENDERS, TRIAGE_TENDERS]))

        net = Category(name="Network Security", keywords=["firewall"])
        cyber = Category(name="Cyber Security", keywords=["vapt"])
        db.add_all([net, cyber])
        alpha = Site(name="Alpha", url="https://alpha.test/t", strategy="positional")
        beta = Site(name="Beta", url="https://beta.test/t", strategy="positional")
        db.add_all([alpha, beta])
        await db.commit()
        for o in (net, cyber, alpha, beta):
            await db.refresh(o)

        # As a scheduled scrape would leave them: stored, in no list.
        tenders = [
            Tender(title="Firewall appliances for head office", date=date(2026, 6, 1),
                   site_id=alpha.id, source_name="Alpha",
                   category_id=net.id, category="Network Security", confidence=0.9),
            Tender(title="VAPT services", date=date(2026, 6, 2),
                   site_id=beta.id, source_name="Beta",
                   category_id=cyber.id, category="Cyber Security", confidence=0.8),
            Tender(title="Canteen management", date=date(2026, 6, 3),
                   site_id=alpha.id, source_name="Alpha"),
        ]
        db.add_all(tenders)
        await db.commit()
        for t in tenders:
            await db.refresh(t)
        return {
            "tenders": [t.id for t in tenders],
            "alpha": alpha.id, "net": net.id,
        }


async def main():
    ids = await seed()

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async def token(u, p):
            r = await c.post("/api/v1/authenticate", json={"identifier": u, "password": p})
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        admin = await token("admin", "AdminPassword123")
        viewer = await token("viewer", "ViewerPassword1")

        print("=== the review inbox ===")
        r = await c.get("/api/v1/tenders?scope=unsaved&uncategorised=include", headers=admin)
        check("everything scraped is waiting", r.json()["total"], 3)
        r = await c.get("/api/v1/tenders?scope=saved&uncategorised=include", headers=admin)
        check("and nothing is saved yet", r.json()["total"], 0)

        r = await c.get("/api/v1/tenders/summary?scope=unsaved", headers=admin)
        check("the summary counts the inbox", r.json()["total"], 3)

        print("\n=== filters work in the inbox ===")
        r = await c.get(
            f"/api/v1/tenders?scope=unsaved&category_id={ids['net']}", headers=admin)
        check("by category", r.json()["total"], 1)
        r = await c.get(
            f"/api/v1/tenders?scope=unsaved&site_id={ids['alpha']}&uncategorised=include",
            headers=admin)
        check("by site", r.json()["total"], 2)
        r = await c.get("/api/v1/tenders?scope=unsaved&uncategorised=only", headers=admin)
        check("uncategorised only", r.json()["total"], 1)

        print("\n=== select all covers the whole inbox ===")
        r = await c.get(
            "/api/v1/tenders/ids?scope=unsaved&uncategorised=include", headers=admin)
        check("every id returned", r.json()["count"], 3)
        every = r.json()["tender_ids"]

        print("\n=== keeping a selection ===")
        r = await c.post("/api/v1/searches/from-tenders", headers=viewer,
                         json={"tender_ids": every[:1]})
        check("keeping needs save_lists", r.status_code, 403)

        r = await c.post("/api/v1/searches/from-tenders", headers=admin,
                         json={"tender_ids": []})
        check("keeping nothing is rejected", r.status_code, 422)

        r = await c.post("/api/v1/searches/from-tenders", headers=admin,
                         json={"tender_ids": [ids["tenders"][0], ids["tenders"][1]]})
        check("created", r.status_code, 201)
        created = r.json()
        check("counts what was kept", created["tender_count"], 2)
        check("sites taken from the tenders", sorted(created["site_names"]),
              ["Alpha", "Beta"])
        check("categories too", sorted(created["category_names"]),
              ["Cyber Security", "Network Security"])
        check("recorded who kept them", created["created_by_username"], "admin")

        r = await c.get("/api/v1/tenders?scope=unsaved&uncategorised=include", headers=admin)
        check("the inbox shrinks", r.json()["total"], 1)
        r = await c.get("/api/v1/tenders?scope=saved&uncategorised=include", headers=admin)
        check("and the registry grows", r.json()["total"], 2)

        r = await c.get("/api/v1/searches", headers=admin)
        check("it appears as a saved list", len(r.json()), 1)
        r = await c.get(f"/api/v1/searches/{created['id']}/tenders", headers=admin)
        check("holding the right tenders", r.json()["total"], 2)

        print("\n=== nothing can be kept twice ===")
        r = await c.post("/api/v1/searches/from-tenders", headers=admin,
                         json={"tender_ids": [ids["tenders"][0]]})
        check("already kept is rejected", r.status_code, 400)
        check("and says why", "already in a list" in r.json()["detail"], True)

        print("\n=== adding to an existing list ===")
        r = await c.post("/api/v1/searches/from-tenders", headers=admin,
                         json={"tender_ids": [ids["tenders"][2]],
                               "search_id": created["id"]})
        check("added", r.status_code, 201)
        check("count grew", r.json()["tender_count"], 3)
        check("uncategorised now included", r.json()["include_uncategorised"], True)

        r = await c.get("/api/v1/tenders?scope=unsaved&uncategorised=include", headers=admin)
        check("the inbox is empty", r.json()["total"], 0)

        r = await c.post("/api/v1/searches/from-tenders", headers=admin,
                         json={"tender_ids": [ids["tenders"][0]], "search_id": 9999})
        check("adding to a missing list is a 404", r.status_code, 404)

        async with AsyncSessionLocal() as db:
            links = (await db.execute(
                select(func.count()).select_from(search_tenders))).scalar_one()
            lists = (await db.execute(select(func.count()).select_from(Search))).scalar_one()
            tenders = (await db.execute(select(func.count()).select_from(Tender))).scalar_one()
        check("one list", lists, 1)
        check("three links", links, 3)
        check("tenders stored once", tenders, 3)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL REVIEW CHECKS PASSED")


asyncio.run(main())

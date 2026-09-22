"""Tests for the admin clear action.

Clearing is irreversible, so this checks both that it removes what it should
and that it leaves the configuration alone.

Run with:  PYTHONPATH=. python tests/maintenance_test.py
"""

import asyncio
import os
from pathlib import Path

DB = Path(__file__).parent / "maintenance_test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.core.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    SAVE_LISTS,
    SEARCH_TENDERS,
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
        db.add(User(username="staff", full_name="Staff", email="s@x.com",
                    password_hash=hash_password("StaffPassword123"),
                    capabilities=[SEARCH_TENDERS, SAVE_LISTS]))
        site = Site(name="Alpha", url="https://alpha.test/t", strategy="positional")
        category = Category(name="Network Security", keywords=["firewall"])
        db.add_all([site, category])
        await db.commit()
        await db.refresh(site)
        await db.refresh(category)

        tenders = [
            Tender(title=f"Tender number {i}", site_id=site.id, source_name="Alpha",
                   category_id=category.id, category="Network Security")
            for i in range(5)
        ]
        db.add_all(tenders)
        await db.commit()
        for t in tenders:
            await db.refresh(t)

        listed = Search(site_ids=[site.id], site_names=["Alpha"],
                        category_ids=[category.id], category_names=["Network Security"],
                        saved=True, status="completed", tender_count=3)
        db.add(listed)
        await db.flush()
        for t in tenders[:3]:
            await db.execute(
                search_tenders.insert().values(search_id=listed.id, tender_id=t.id)
            )
        await db.commit()


async def counts():
    async with AsyncSessionLocal() as db:
        return {
            "searches": (await db.execute(select(func.count()).select_from(Search))).scalar_one(),
            "links": (await db.execute(select(func.count()).select_from(search_tenders))).scalar_one(),
            "tenders": (await db.execute(select(func.count()).select_from(Tender))).scalar_one(),
            "sites": (await db.execute(select(func.count()).select_from(Site))).scalar_one(),
            "categories": (await db.execute(select(func.count()).select_from(Category))).scalar_one(),
            "users": (await db.execute(select(func.count()).select_from(User))).scalar_one(),
        }


async def main():
    await seed()

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async def token(username, password):
            r = await c.post("/api/v1/authenticate",
                             json={"identifier": username, "password": password})
            return {"Authorization": f"Bearer {r.json()['access_token']}"}

        admin = await token("admin", "AdminPassword123")
        staff = await token("staff", "StaffPassword123")

        print("=== who may clear ===")
        r = await c.post("/api/v1/admin/clear", headers=staff,
                         json={"scope": "lists", "confirm": "CLEAR"})
        check("needs the admin capability", r.status_code, 403)
        r = await c.post("/api/v1/admin/clear", json={"scope": "lists", "confirm": "CLEAR"})
        check("needs a token", r.status_code, 401)

        print("\n=== the confirmation is required ===")
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "lists", "confirm": ""})
        check("empty confirmation rejected", r.status_code, 400)
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "lists", "confirm": "clear"})
        check("wrong case rejected", r.status_code, 400)
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "nonsense", "confirm": "CLEAR"})
        check("unknown scope rejected", r.status_code, 422)

        before = await counts()
        check("nothing removed by the failed attempts", before["searches"], 1)

        print("\n=== preview ===")
        r = await c.get("/api/v1/admin/clear", headers=admin)
        check("counts the saved lists", r.json()["saved_lists"], 1)
        check("counts the kept tenders", r.json()["saved_tenders"], 3)
        check("counts every stored tender", r.json()["stored_tenders"], 5)

        print("\n=== clearing lists keeps the tenders ===")
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "lists", "confirm": "CLEAR"})
        check("accepted", r.status_code, 200)
        check("reported the lists removed", r.json()["lists_removed"], 1)
        check("reported the tenders kept", r.json()["tenders_kept"], 5)

        after = await counts()
        check("saved lists gone", after["searches"], 0)
        check("links gone", after["links"], 0)
        check("tenders untouched", after["tenders"], 5)
        check("sites untouched", after["sites"], 1)
        check("categories untouched", after["categories"], 1)
        check("users untouched", after["users"], 2)

        r = await c.get("/api/v1/tenders?status=all", headers=admin)
        check("saved tenders page is empty", r.json()["total"], 0)
        r = await c.get("/api/v1/tenders?status=all&scope=all", headers=admin)
        check("but everything scraped still shows them", r.json()["total"], 5)

        print("\n=== clearing everything ===")
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "everything", "confirm": "CLEAR"})
        check("reported the tenders removed", r.json()["tenders_removed"], 5)

        final = await counts()
        check("tenders gone", final["tenders"], 0)
        check("sites still there", final["sites"], 1)
        check("categories still there", final["categories"], 1)
        check("users still there", final["users"], 2)

        print("\n=== clearing an already empty database is harmless ===")
        r = await c.post("/api/v1/admin/clear", headers=admin,
                         json={"scope": "everything", "confirm": "CLEAR"})
        check("still succeeds", r.status_code, 200)
        check("removed nothing", r.json()["tenders_removed"], 0)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL MAINTENANCE CHECKS PASSED")


asyncio.run(main())

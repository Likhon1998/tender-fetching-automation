"""End-to-end test of the tender browse, filter, sort and triage endpoints.

Runs against a throwaway SQLite database, so it never touches Supabase.
Run with:  PYTHONPATH=. python tests/tenders_test.py
"""

import asyncio, os
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).parent / "tenders_test.db"
if DB.exists(): DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"

import httpx
from sqlalchemy import select
from app.main import app as fastapi_app
from app.db.session import engine, AsyncSessionLocal
from app.db.base import Base
import app.models as _m
from app.models.category import Category
from app.models.site import Site
from app.models.search import Search, search_tenders
from app.models.tender import Tender
from app.core.capabilities import ALL_CAPABILITIES, SAVE_LISTS, SEARCH_TENDERS, TRIAGE_TENDERS
from app.models.user import User
from app.core.security import hash_password


async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)

    today = date.today()
    async with AsyncSessionLocal() as db:
        db.add(User(username="admin", full_name="Admin", email="a@x.com",
                    password_hash=hash_password("AdminPassword123"), capabilities=list(ALL_CAPABILITIES)))
        db.add(User(username="staff", full_name="Staff", email="s@x.com",
                    password_hash=hash_password("StaffPassword123"), capabilities=[SEARCH_TENDERS, SAVE_LISTS, TRIAGE_TENDERS]))
        net = Category(name="Network Security", keywords=["firewall"])
        soft = Category(name="Software Development", keywords=["web"])
        db.add_all([net, soft])
        s1 = Site(name="AlphaBank", url="https://alpha.test/tender")
        s2 = Site(name="BetaGov", url="https://beta.test/notices")
        db.add_all([s1, s2])
        await db.commit()
        await db.refresh(net); await db.refresh(soft)
        await db.refresh(s1); await db.refresh(s2)

        db.add_all([
            Tender(title="Firewall procurement", date=today - timedelta(days=5),
                   date_raw="recent", site_id=s1.id, source_name="AlphaBank",
                   category_id=net.id, category="Network Security", confidence=0.9),
            Tender(title="Website redevelopment", date=today - timedelta(days=40),
                   site_id=s2.id, source_name="BetaGov",
                   category_id=soft.id, category="Software Development", confidence=0.7),
            Tender(title="Old firewall notice", date=date(2020, 3, 1),
                   site_id=s1.id, source_name="AlphaBank",
                   category_id=net.id, category="Network Security", confidence=0.6),
            Tender(title="Canteen management services", date=today,
                   site_id=s2.id, source_name="BetaGov"),          # unclassified
            Tender(title="Undated firewall tender", date=None, date_raw="",
                   site_id=s1.id, source_name="AlphaBank",
                   category_id=net.id, category="Network Security", confidence=0.5),
            Tender(title="Dismissed item", date=today, site_id=s1.id,
                   source_name="AlphaBank", category_id=net.id,
                   category="Network Security", confidence=0.8, status="not_interested"),
            # Deadlines at a spread of distances, for the "submission within"
            # filter. One has already passed and must never be offered.
            Tender(title="Closing in five days", date=today, site_id=s1.id,
                   source_name="AlphaBank", category_id=net.id, category="Network Security",
                   confidence=0.7, date_type="submission",
                   submission_date=today + timedelta(days=5), submission_date_raw="soon"),
            Tender(title="Closing in three weeks", date=today, site_id=s1.id,
                   source_name="AlphaBank", category_id=net.id, category="Network Security",
                   confidence=0.7, submission_date=today + timedelta(weeks=3)),
            Tender(title="Closing in ten weeks", date=today, site_id=s1.id,
                   source_name="AlphaBank", category_id=net.id, category="Network Security",
                   confidence=0.7, submission_date=today + timedelta(weeks=10)),
            Tender(title="Deadline already passed", date=today, site_id=s1.id,
                   source_name="AlphaBank", category_id=net.id, category="Network Security",
                   confidence=0.7, submission_date=today - timedelta(days=3)),
        ])
        await db.commit()

        # The registry shows tenders kept in a saved list, so put every seeded
        # tender into one. scope=all is checked separately below.
        every = (await db.execute(select(Tender.id))).scalars().all()
        listed = Search(
            site_ids=[s1.id, s2.id], site_names=["AlphaBank", "BetaGov"],
            category_ids=[], category_names=[], saved=True,
            status="completed", tender_count=len(every),
        )
        db.add(listed)
        await db.flush()
        for tid in every:
            await db.execute(
                search_tenders.insert().values(search_id=listed.id, tender_id=tid)
            )
        await db.commit()

    t = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=t, base_url="http://test") as c:
        async def login(u, p):
            r = await c.post("/api/v1/authenticate", json={"identifier": u, "password": p})
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        admin = await login("admin", "AdminPassword123")
        staff = await login("staff", "StaffPassword123")

        r = await c.get("/api/v1/tenders")
        print("no token:", r.status_code); assert r.status_code == 401

        # default: status=new, classified only -> 4 of the 6
        r = await c.get("/api/v1/tenders", headers=staff)
        d = r.json()
        titles = [i["title"] for i in d["items"]]
        print("default list:", r.status_code, "total:", d["total"])
        print("  ", titles)
        assert d["total"] == 8, d["total"]
        assert "Dismissed item" not in titles           # not_interested hidden
        assert "Canteen management services" not in titles  # unclassified hidden

        # undated rows sort last even though sorting desc by date
        print("default sort (date desc):", titles)
        assert titles[-1] == "Undated firewall tender"

        r = await c.get("/api/v1/tenders?uncategorised=include", headers=staff)
        print("uncategorised=include:", r.json()["total"]); assert r.json()["total"] == 9

        r = await c.get("/api/v1/tenders?uncategorised=only", headers=staff)
        d = r.json()
        print("uncategorised=only:", d["total"], [i["title"] for i in d["items"]])
        assert d["total"] == 1
        assert all(i["category"] is None for i in d["items"])

        r = await c.get("/api/v1/tenders?uncategorised=bogus", headers=staff)
        print("invalid uncategorised value:", r.status_code); assert r.status_code == 422

        r = await c.get("/api/v1/tenders?status=all&uncategorised=include", headers=staff)
        print("status=all + uncategorised:", r.json()["total"]); assert r.json()["total"] == 10

        r = await c.get("/api/v1/tenders?status=not_interested", headers=staff)
        print("status=not_interested:", r.json()["total"]); assert r.json()["total"] == 1

        # search
        r = await c.get("/api/v1/tenders?search=firewall", headers=staff)
        print("search 'firewall':", r.json()["total"]); assert r.json()["total"] == 3
        r = await c.get("/api/v1/tenders?search=FIREWALL", headers=staff)
        print("search case-insensitive:", r.json()["total"]); assert r.json()["total"] == 3

        # filter by category and site
        async with AsyncSessionLocal() as db:
            net_id = (await db.execute(select(Category.id).where(Category.name=="Network Security"))).scalar_one()
            beta_id = (await db.execute(select(Site.id).where(Site.name=="BetaGov"))).scalar_one()
        r = await c.get(f"/api/v1/tenders?category_id={net_id}", headers=staff)
        print("by category:", r.json()["total"]); assert r.json()["total"] == 7
        r = await c.get(f"/api/v1/tenders?site_id={beta_id}", headers=staff)
        print("by site:", r.json()["total"]); assert r.json()["total"] == 1

        # date cutoff keeps undated rows
        cutoff = (today - timedelta(days=365)).isoformat()
        r = await c.get(f"/api/v1/tenders?date_from={cutoff}", headers=staff)
        got = [i["title"] for i in r.json()["items"]]
        print("date_from last year:", r.json()["total"], got)
        assert "Old firewall notice" not in got
        assert "Undated firewall tender" in got   # undated kept, not dropped

        # sorting
        r = await c.get("/api/v1/tenders?sort=title&order=asc", headers=staff)
        got = [i["title"] for i in r.json()["items"]]
        print("sort title asc:", got); assert got == sorted(got)

        r = await c.get("/api/v1/tenders?sort=confidence&order=desc", headers=staff)
        conf = [float(i["confidence"]) for i in r.json()["items"]]
        print("sort confidence desc:", conf); assert conf == sorted(conf, reverse=True)

        # pagination
        r = await c.get("/api/v1/tenders?page_size=2&page=1&status=all&uncategorised=include", headers=staff)
        d = r.json()
        print("page 1 of", d["pages"], "size", len(d["items"]))
        assert len(d["items"]) == 2 and d["total"] == 10
        first_page = {i["id"] for i in d["items"]}
        r = await c.get("/api/v1/tenders?page_size=2&page=2&status=all&uncategorised=include", headers=staff)
        assert not (first_page & {i["id"] for i in r.json()["items"]}), "pages overlap"
        print("page 2 has no overlap with page 1")

        # A browser submits `category_id=` for an unselected dropdown; that
        # must read as "no filter" rather than failing validation.
        r = await c.get(
            "/api/v1/tenders?search=&category_id=&site_id=&date_from=&status=new",
            headers=staff,
        )
        print("blank query params:", r.status_code, "total:", r.json()["total"])
        assert r.status_code == 200 and r.json()["total"] == 8

        r = await c.get("/api/v1/tenders?page_size=500", headers=staff)
        print("page_size over limit:", r.status_code); assert r.status_code == 422

        # triage
        target = (await c.get("/api/v1/tenders", headers=staff)).json()["items"][0]
        r = await c.patch(f"/api/v1/tenders/{target['id']}",
                          headers=staff, json={"status": "not_interested"})
        print("triage as staff:", r.status_code, r.json()["status"]); assert r.status_code == 200
        r = await c.get("/api/v1/tenders", headers=staff)
        print("  disappears from default view, total now:", r.json()["total"])
        assert r.json()["total"] == 7

        r = await c.patch(f"/api/v1/tenders/{target['id']}", headers=staff, json={"status": "new"})
        print("restore:", r.status_code); assert r.status_code == 200
        r = await c.patch(f"/api/v1/tenders/{target['id']}", headers=staff, json={"status": "bogus"})
        print("invalid status:", r.status_code); assert r.status_code == 422

        r = await c.get("/api/v1/tenders/999999", headers=staff)
        print("missing tender:", r.status_code); assert r.status_code == 404

        # summary
        print("\n=== submission deadline filter ===")
        for window, expected in [
            ("1", ["Closing in five days"]),
            ("4", ["Closing in five days", "Closing in three weeks"]),
            ("4plus", ["Closing in ten weeks"]),
        ]:
            r = await c.get(
                f"/api/v1/tenders?submission_within={window}&status=all", headers=staff
            )
            got = sorted(i["title"] for i in r.json()["items"])
            print(f"  within {window}: {got}")
            assert got == sorted(expected), (window, got)

        r = await c.get("/api/v1/tenders?submission_within=1&status=all", headers=staff)
        assert not any("passed" in i["title"] for i in r.json()["items"])
        print("  past deadlines excluded")

        r = await c.get("/api/v1/tenders?submission_within=9&status=all", headers=staff)
        print("  invalid window:", r.status_code)
        assert r.status_code == 422

        r = await c.get(
            "/api/v1/tenders?sort=submission_date&order=asc&status=all", headers=staff
        )
        print("  sort by deadline:", r.status_code)
        assert r.status_code == 200

        r = await c.get("/api/v1/tenders?status=all", headers=staff)
        first = r.json()["items"][0]
        assert "date_type" in first and "submission_date" in first
        print("  date_type exposed:", first["date_type"])

        r = await c.get("/api/v1/tenders/summary", headers=staff)
        print("summary:", r.json())
        assert r.json()["total"] == 10 and r.json()["unclassified"] == 1

        # A tender that was scraped but never saved stays out of the registry.
        async with AsyncSessionLocal() as db:
            db.add(Tender(title="Scraped but never saved", site_id=s1.id,
                          source_name="AlphaBank", category_id=net_id,
                          category="Network Security", confidence=0.7))
            await db.commit()
        r = await c.get("/api/v1/tenders?status=all", headers=staff)
        titles = [i["title"] for i in r.json()["items"]]
        print("unsaved tender hidden:", "Scraped but never saved" not in titles)
        assert "Scraped but never saved" not in titles
        r = await c.get("/api/v1/tenders?status=all&scope=all", headers=staff)
        titles = [i["title"] for i in r.json()["items"]]
        print("scope=all reveals it:", "Scraped but never saved" in titles)
        assert "Scraped but never saved" in titles

        # site delete blocked while tenders reference it
        async with AsyncSessionLocal() as db:
            alpha_id = (await db.execute(select(Site.id).where(Site.name=="AlphaBank"))).scalar_one()
        r = await c.delete(f"/api/v1/sites/{alpha_id}", headers=admin)
        print("delete site with tenders:", r.status_code, "-", r.json()["detail"])
        assert r.status_code == 409

        r = await c.post("/api/v1/sites", headers=admin,
                         json={"name": "Unused", "url": "https://unused.test/"})
        unused_id = r.json()["id"]
        r = await c.delete(f"/api/v1/sites/{unused_id}", headers=admin)
        print("delete site without tenders:", r.status_code); assert r.status_code == 204

    await engine.dispose()
    print("\nALL TENDER CHECKS PASSED")

asyncio.run(main())

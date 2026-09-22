"""End-to-end test of the categories and sites CRUD endpoints.

Runs against a throwaway SQLite database, so it never touches Supabase.
Run with:  PYTHONPATH=. python tests/reference_test.py
"""

import asyncio, os
from pathlib import Path

DB = Path(__file__).parent / "reference_test.db"
if DB.exists(): DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"

import httpx
from sqlalchemy import select
from app.main import app as fastapi_app
from app.db.session import engine, AsyncSessionLocal
from app.db.base import Base
import app.models as _m
from app.core.capabilities import ALL_CAPABILITIES, SAVE_LISTS, SEARCH_TENDERS, TRIAGE_TENDERS
from app.models.user import User
from app.models.category import Category
from app.models.site import Site
from app.core.security import hash_password
from app.data.reference_data import CATEGORIES, SITES

async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)

    # seed users + reference data
    async with AsyncSessionLocal() as db:
        db.add(User(username="admin", full_name="Admin", email="admin@x.com",
                    password_hash=hash_password("AdminPassword123"), capabilities=list(ALL_CAPABILITIES)))
        db.add(User(username="normal", full_name="Normal", email="n@x.com",
                    password_hash=hash_password("UserPassword123"), capabilities=[SEARCH_TENDERS, SAVE_LISTS, TRIAGE_TENDERS]))
        for s in CATEGORIES: db.add(Category(**s))
        for s in SITES: db.add(Site(**s))
        await db.commit()

    t = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=t, base_url="http://test") as c:
        async def login(u,p):
            r = await c.post("/api/v1/authenticate", json={"identifier":u,"password":p})
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        admin = await login("admin","AdminPassword123")
        user = await login("normal","UserPassword123")

        r = await c.get("/api/v1/categories", headers=user)
        print("list categories (user):", r.status_code, len(r.json()))
        assert r.status_code==200 and len(r.json())==15
        print("  first:", r.json()[0]["name"], "| keywords:", len(r.json()[0]["keywords"]))
        assert sum(len(c["keywords"]) for c in r.json()) > 1000, "keyword lists look too thin"

        r = await c.get("/api/v1/sites", headers=user)
        print("list sites (user):", r.status_code, len(r.json()))
        assert len(r.json())==38

        r = await c.get("/api/v1/categories")
        print("list categories (no token):", r.status_code); assert r.status_code==401

        # create as normal user -> 403
        r = await c.post("/api/v1/categories", headers=user, json={"name":"Hacky","keywords":[]})
        print("create category as user:", r.status_code); assert r.status_code==403

        # create as admin
        r = await c.post("/api/v1/categories", headers=admin,
                         json={"name":"  Test  Category ","description":"d","keywords":["  FOO ","foo","Bar"]})
        print("create category as admin:", r.status_code, repr(r.json()["name"]), r.json()["keywords"])
        assert r.status_code==201
        assert r.json()["name"]=="Test Category"
        assert r.json()["keywords"]==["foo","bar"]  # trimmed, lowered, deduped
        cid = r.json()["id"]

        # duplicate name, different case
        r = await c.post("/api/v1/categories", headers=admin, json={"name":"test category","keywords":[]})
        print("duplicate category:", r.status_code); assert r.status_code==409

        # patch
        r = await c.patch(f"/api/v1/categories/{cid}", headers=admin, json={"description":"updated"})
        print("patch category:", r.status_code, r.json()["description"], "| name kept:", r.json()["name"])
        assert r.status_code==200 and r.json()["name"]=="Test Category"

        r = await c.patch(f"/api/v1/categories/{cid}", headers=admin, json={})
        print("patch empty:", r.status_code); assert r.status_code==400

        r = await c.delete(f"/api/v1/categories/{cid}", headers=admin)
        print("delete category:", r.status_code); assert r.status_code==204
        r = await c.get(f"/api/v1/categories/{cid}", headers=admin)
        print("get deleted:", r.status_code); assert r.status_code==404

        # sites
        r = await c.post("/api/v1/sites", headers=admin, json={"name":"TestSite","url":"not-a-url"})
        print("bad url:", r.status_code); assert r.status_code==422

        r = await c.post("/api/v1/sites", headers=admin,
                         json={"name":"TestSite","url":"https://example.com/tenders","strategy":"table"})
        print("create site:", r.status_code, r.json()["url"], "active:", r.json()["active"])
        assert r.status_code==201 and r.json()["active"] is True
        sid = r.json()["id"]

        r = await c.patch(f"/api/v1/sites/{sid}", headers=admin, json={"active": False})
        print("deactivate site:", r.status_code, "active:", r.json()["active"])
        assert r.json()["active"] is False

        r = await c.get("/api/v1/sites?active_only=true", headers=user)
        print("active_only sites:", r.status_code, len(r.json()))
        assert len(r.json())==38  # the new one is inactive

        r = await c.get("/api/v1/sites", headers=user)
        assert len(r.json())==39
        print("all sites:", len(r.json()))

        r = await c.delete(f"/api/v1/sites/{sid}", headers=user)
        print("delete site as user:", r.status_code); assert r.status_code==403
        r = await c.delete(f"/api/v1/sites/{sid}", headers=admin)
        print("delete site as admin:", r.status_code); assert r.status_code==204

    await engine.dispose()
    print("\nALL REFERENCE CHECKS PASSED")

asyncio.run(main())

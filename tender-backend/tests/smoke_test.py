"""End-to-end test of authentication and the capability system.

There is no self-registration: the first admin is seeded, and every other
account is created by someone holding manage_users. This runs against a
throwaway SQLite database, so it never touches Supabase.

Run with:  PYTHONPATH=. python tests/smoke_test.py
"""

import asyncio
import os
from pathlib import Path

DB = Path(__file__).parent / "smoke.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.core.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    MANAGE_SITES,
    SAVE_LISTS,
    SEARCH_TENDERS,
    TRIAGE_TENDERS,
)
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.user import User, UserStatus  # noqa: E402

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # The seeded first admin, as scripts/seed_admin.py would create it.
    async with AsyncSessionLocal() as db:
        db.add(User(username="admin", full_name="Admin", email="admin@x.com",
                    password_hash=hash_password("AdminPassword123"),
                    capabilities=list(ALL_CAPABILITIES)))
        await db.commit()

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async def login(username, password):
            r = await c.post("/api/v1/authenticate",
                             json={"identifier": username, "password": password})
            return r

        print("=== there is no public registration ===")
        r = await c.post("/api/v1/registration", json={
            "username": "sneaky", "full_name": "S", "email": "s@x.com",
            "password": "SneakyPassword1", "confirm_password": "SneakyPassword1"})
        check("registration endpoint is gone", r.status_code, 404)

        print("\n=== signing in ===")
        r = await login("admin", "AdminPassword123")
        check("admin can sign in", r.status_code, 200)
        admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        check("token carries no role claim", "role" in r.json(), False)

        r = await login("admin", "WrongPassword1")
        check("wrong password rejected", r.status_code, 401)
        r2 = await login("ghost", "WrongPassword1")
        check("unknown user gives the same message",
              r.json()["detail"], r2.json()["detail"])

        r = await c.get("/api/v1/me", headers=admin_headers)
        check("me returns capabilities", len(r.json()["capabilities"]), len(ALL_CAPABILITIES))

        r = await c.get("/api/v1/me")
        check("me needs a token", r.status_code, 401)
        r = await c.get("/api/v1/me", headers={"Authorization": "Bearer nonsense"})
        check("bad token rejected", r.status_code, 401)

        print("\n=== changing your own password ===")
        r = await c.post("/api/v1/change-password", headers=admin_headers, json={
            "current_password": "WrongPassword1",
            "new_password": "BrandNewPassword1",
            "confirm_password": "BrandNewPassword1"})
        check("wrong current password rejected", r.status_code, 401)

        r = await c.post("/api/v1/change-password", headers=admin_headers, json={
            "current_password": "AdminPassword123",
            "new_password": "BrandNewPassword1",
            "confirm_password": "Different12345"})
        check("mismatched new passwords rejected", r.status_code, 422)

        r = await c.post("/api/v1/change-password", headers=admin_headers, json={
            "current_password": "AdminPassword123",
            "new_password": "AdminPassword123",
            "confirm_password": "AdminPassword123"})
        check("reusing the same password rejected", r.status_code, 422)

        r = await c.post("/api/v1/change-password", headers=admin_headers, json={
            "current_password": "AdminPassword123",
            "new_password": "BrandNewPassword1",
            "confirm_password": "BrandNewPassword1"})
        check("password changed", r.status_code, 200)
        check("no hash in the response", "password_hash" in r.text, False)

        check("old password no longer works",
              (await login("admin", "AdminPassword123")).status_code, 401)
        r = await login("admin", "BrandNewPassword1")
        check("new password works", r.status_code, 200)
        admin_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.post("/api/v1/change-password", json={
            "current_password": "x", "new_password": "BrandNewPassword2",
            "confirm_password": "BrandNewPassword2"})
        check("needs a token", r.status_code, 401)

        print("\n=== the capability catalogue ===")
        r = await c.get("/api/v1/users/capabilities", headers=admin_headers)
        check("every capability is described", len(r.json()), len(ALL_CAPABILITIES))
        check("each has a description", all(x["description"] for x in r.json()), True)

        print("\n=== the admin creates a search-only user ===")
        r = await c.post("/api/v1/users", headers=admin_headers, json={
            "username": "searcher", "full_name": "Search Only",
            "email": "searcher@x.com",
            "password": "SearchPassword1", "confirm_password": "SearchPassword1",
            "capabilities": [SEARCH_TENDERS],
        })
        check("created", r.status_code, 201)
        check("holds only what was granted", r.json()["capabilities"], [SEARCH_TENDERS])
        check("no password in the response", "password" in r.text, False)

        r = await c.post("/api/v1/users", headers=admin_headers, json={
            "username": "searcher", "full_name": "Duplicate Name", "email": "other@x.com",
            "password": "SearchPassword1", "confirm_password": "SearchPassword1",
            "capabilities": []})
        check("duplicate username rejected", r.status_code, 409)

        r = await c.post("/api/v1/users", headers=admin_headers, json={
            "username": "bad", "full_name": "Bad Match", "email": "b@x.com",
            "password": "SearchPassword1", "confirm_password": "Different12345",
            "capabilities": []})
        check("mismatched passwords rejected", r.status_code, 422)

        r = await c.post("/api/v1/users", headers=admin_headers, json={
            "username": "odd", "full_name": "Odd One", "email": "o@x.com",
            "password": "SearchPassword1", "confirm_password": "SearchPassword1",
            "capabilities": ["search_tenders", "make_me_king"]})
        check("unknown capability dropped", r.json()["capabilities"], [SEARCH_TENDERS])

        print("\n=== capabilities are enforced ===")
        r = await login("searcher", "SearchPassword1")
        searcher = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = await c.get("/api/v1/sites", headers=searcher)
        check("can read sites", r.status_code, 200)
        r = await c.post("/api/v1/sites", headers=searcher,
                         json={"name": "X", "url": "https://x.test/"})
        check("cannot manage sites", r.status_code, 403)
        check("the error says what is needed", "manage sites" in r.json()["detail"], True)

        r = await c.get("/api/v1/users", headers=searcher)
        check("cannot list users", r.status_code, 403)
        r = await c.post("/api/v1/admin/reclassify", headers=searcher)
        check("cannot run admin tasks", r.status_code, 403)

        print("\n=== granting a capability takes effect immediately ===")
        users = (await c.get("/api/v1/users", headers=admin_headers)).json()
        searcher_id = next(u["id"] for u in users if u["username"] == "searcher")

        r = await c.patch(f"/api/v1/users/{searcher_id}", headers=admin_headers,
                          json={"capabilities": [SEARCH_TENDERS, MANAGE_SITES]})
        check("capability added", sorted(r.json()["capabilities"]),
              sorted([SEARCH_TENDERS, MANAGE_SITES]))

        # The same token from before: capabilities come from the database, not
        # the token, so no new sign-in is needed.
        r = await c.post("/api/v1/sites", headers=searcher,
                         json={"name": "NewSite", "url": "https://new.test/"})
        check("can now manage sites on the old token", r.status_code, 201)

        r = await c.patch(f"/api/v1/users/{searcher_id}", headers=admin_headers,
                          json={"capabilities": [SEARCH_TENDERS]})
        r = await c.post("/api/v1/sites", headers=searcher,
                         json={"name": "Another", "url": "https://another.test/"})
        check("and loses it immediately when revoked", r.status_code, 403)

        print("\n=== disabled accounts are locked out ===")
        r = await c.patch(f"/api/v1/users/{searcher_id}", headers=admin_headers,
                          json={"status": "disabled"})
        check("disabled", r.json()["status"], "disabled")
        r = await c.get("/api/v1/me", headers=searcher)
        check("existing token stops working", r.status_code, 403)
        r = await login("searcher", "SearchPassword1")
        check("cannot sign in again", r.status_code, 403)
        await c.patch(f"/api/v1/users/{searcher_id}", headers=admin_headers,
                      json={"status": "active"})

        print("\n=== the last admin cannot lock everyone out ===")
        admin_id = next(u["id"] for u in users if u["username"] == "admin")
        r = await c.patch(f"/api/v1/users/{admin_id}", headers=admin_headers,
                          json={"capabilities": [SEARCH_TENDERS]})
        check("cannot drop the only manage_users", r.status_code, 409)
        r = await c.patch(f"/api/v1/users/{admin_id}", headers=admin_headers,
                          json={"status": "disabled"})
        check("cannot disable the only admin", r.status_code, 409)
        r = await c.delete(f"/api/v1/users/{admin_id}", headers=admin_headers)
        check("cannot delete your own account", r.status_code, 409)

        print("\n=== a second admin removes that restriction ===")
        r = await c.post("/api/v1/users", headers=admin_headers, json={
            "username": "admin2", "full_name": "Second Admin", "email": "a2@x.com",
            "password": "AdminPassword2", "confirm_password": "AdminPassword2",
            "capabilities": list(ALL_CAPABILITIES)})
        check("second admin created", r.status_code, 201)
        second_id = r.json()["id"]

        r = await c.patch(f"/api/v1/users/{admin_id}", headers=admin_headers,
                          json={"capabilities": [SEARCH_TENDERS, SAVE_LISTS, TRIAGE_TENDERS]})
        check("first admin can now step down", r.status_code, 200)

        r = await c.get("/api/v1/users", headers=admin_headers)
        check("and loses access to user management", r.status_code, 403)

        print("\n=== deleting a user ===")
        r2 = await login("admin2", "AdminPassword2")
        admin2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        r = await c.delete(f"/api/v1/users/{searcher_id}", headers=admin2)
        check("deleted", r.status_code, 204)
        r = await c.patch(f"/api/v1/users/{searcher_id}", headers=admin2, json={"status": "active"})
        check("gone", r.status_code, 404)

        async with AsyncSessionLocal() as db:
            left = (await db.execute(select(User))).scalars().all()
        check("three accounts remain", len(left), 3)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL CHECKS PASSED")


asyncio.run(main())

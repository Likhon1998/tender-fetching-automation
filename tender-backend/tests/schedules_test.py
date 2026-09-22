"""Tests for schedule groups: sets of sites scraped on the same cadence.

The runner is driven directly rather than waiting on the background loop, and
Firecrawl is faked, so this makes no network calls.

Run with:  PYTHONPATH=. python tests/schedules_test.py
"""

import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

DB = Path(__file__).parent / "schedules_test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-use-abcdefgh"
os.environ["FIRECRAWL_API_KEY"] = "fc-test-key"
os.environ["SCHEDULER_ENABLED"] = "false"  # driven by hand here
os.environ["TIMEZONE"] = "Asia/Dhaka"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import app.models as _models  # noqa: E402,F401
from app.core.capabilities import ALL_CAPABILITIES, SEARCH_TENDERS  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.ingestion.firecrawl import FirecrawlError  # noqa: E402
from app.ingestion.parsers import POSITIONAL_COLUMNS, PositionalColumns  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.schedule import ScheduleGroup  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.tender import Tender  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import ingestion_service, scheduler  # noqa: E402
from app.services.schedule_service import compute_next_run  # noqa: E402

failures = []
ZONE = ZoneInfo("Asia/Dhaka")


def as_utc(moment):
    """SQLite drops the timezone that Postgres keeps, so normalise before
    comparing. The application itself compares in SQL, never in Python."""
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


PAD = "<nav>menu</nav><header><h1>Notices</h1><p>Tenders published here.</p></header>"


def page(title):
    return (
        f"<html><body>{PAD}<table>"
        "<tr><th>Date</th><th>Title</th><th>Link</th></tr>"
        f"<tr><td>15-Jun-2026</td><td>{title}</td>"
        '<td><a href="/a.pdf">PDF</a></td></tr>'
        "</table></body></html>"
    )


class FakeFirecrawl:
    def __init__(self, *_, **__):
        self.calls = []

    async def scrape(self, url):
        self.calls.append(url)
        if "broken.test" in url:
            raise FirecrawlError("simulated outage")
        host = url.split("//")[1].split(".")[0]
        return page(f"Procurement of Firewall Appliances for {host}")

    async def aclose(self):
        pass


fake = FakeFirecrawl()


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        db.add(User(username="admin", full_name="Admin", email="a@x.com",
                    password_hash=hash_password("AdminPassword123"),
                    capabilities=list(ALL_CAPABILITIES)))
        db.add(User(username="staff", full_name="Staff", email="s@x.com",
                    password_hash=hash_password("StaffPassword123"),
                    capabilities=[SEARCH_TENDERS]))
        db.add(Category(name="Network Security", keywords=["firewall appliance"]))
        sites = [
            Site(name="Alpha", url="https://alpha.test/t", strategy="positional"),
            Site(name="Beta", url="https://beta.test/t", strategy="positional"),
            Site(name="Gamma", url="https://gamma.test/t", strategy="positional"),
            Site(name="Broken", url="https://broken.test/t", strategy="positional"),
            Site(name="Paused", url="https://pause.test/t",
                 strategy="positional", active=False),
        ]
        db.add_all(sites)
        await db.commit()
        for s in sites:
            await db.refresh(s)
        return {s.name.lower(): s.id for s in sites}


async def main():
    ids = await seed()
    for name in ("Alpha", "Beta", "Gamma", "Broken", "Paused"):
        POSITIONAL_COLUMNS[name] = PositionalColumns(title=1, link=2, date=0, min_cols=3)
    ingestion_service.FirecrawlClient = lambda *a, **k: fake

    print("=== next run calculation ===")
    base = datetime(2026, 9, 3, 10, 0, tzinfo=ZONE)

    def local(freq, at, interval=None):
        return compute_next_run(
            freq, at, interval_days=interval, after=base
        ).astimezone(ZONE)

    check("time already gone runs tomorrow",
          local("daily", time(8, 0)).date(), base.date() + timedelta(days=1))
    check("time still ahead runs today", local("daily", time(18, 0)).date(), base.date())
    check("weekly adds seven days",
          local("weekly", time(8, 0)).date(), base.date() + timedelta(days=7))
    check("biweekly adds fourteen days",
          local("biweekly", time(8, 0)).date(), base.date() + timedelta(days=14))
    check("custom uses its own interval",
          local("custom", time(8, 0), 3).date(), base.date() + timedelta(days=3))
    check("monthly moves to the next month", local("monthly", time(8, 0)).month, 10)
    jan31 = datetime(2027, 1, 31, 10, 0, tzinfo=ZONE)
    check("month end is clamped, not skipped",
          compute_next_run("monthly", time(8, 0), after=jan31).astimezone(ZONE).day, 28)
    check("the local time is preserved", local("weekly", time(6, 30)).hour, 6)

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async def token(u, p):
            r = await c.post("/api/v1/authenticate",
                             json={"identifier": u, "password": p})
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        admin = await token("admin", "AdminPassword123")
        staff = await token("staff", "StaffPassword123")

        print("\n=== permissions ===")
        r = await c.post("/api/v1/schedules", headers=staff, json={
            "site_ids": [ids["alpha"]], "frequency": "daily", "run_at": "08:00:00"})
        check("creating needs manage_schedules", r.status_code, 403)
        check("the error names the permission",
              "manage schedules" in r.json()["detail"], True)
        r = await c.get("/api/v1/schedules", headers=staff)
        check("but anyone signed in may read", r.status_code, 200)
        r = await c.get("/api/v1/schedules")
        check("reading still needs a token", r.status_code, 401)

        print("\n=== the site picker ===")
        r = await c.get("/api/v1/schedules/site-availability", headers=admin)
        rows = r.json()
        check("every site is listed", len(rows), 5)
        check("none are spoken for yet",
              all(row["group_id"] is None for row in rows), True)
        check("ordered by name", [row["site_name"] for row in rows][:2],
              ["Alpha", "Beta"])

        print("\n=== validation ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [], "frequency": "daily", "run_at": "08:00:00"})
        check("no sites rejected", r.status_code, 422)
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [ids["alpha"]], "frequency": "custom", "run_at": "08:00:00"})
        check("custom without an interval rejected", r.status_code, 422)
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [ids["alpha"]], "frequency": "hourly", "run_at": "08:00:00"})
        check("unknown frequency rejected", r.status_code, 422)
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [9999], "frequency": "daily", "run_at": "08:00:00"})
        check("unknown site rejected", r.status_code, 404)

        print("\n=== creating a group ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "name": "Morning banks", "site_ids": [ids["alpha"], ids["beta"]],
            "frequency": "daily", "run_at": "08:00:00"})
        check("created", r.status_code, 201)
        first = r.json()
        check("holds both sites", len(first["sites"]), 2)
        check("sites sorted by name", [s["name"] for s in first["sites"]],
              ["Alpha", "Beta"])
        check("next run calculated", first["next_run_at"] is not None, True)
        check("timezone reported", first["timezone"], "Asia/Dhaka")

        print("\n=== a site cannot be in two groups ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [ids["beta"], ids["gamma"]],
            "frequency": "weekly", "run_at": "09:00:00"})
        check("rejected", r.status_code, 409)
        detail = r.json()["detail"]
        check("the clash is named", detail["clashes"][0]["site_name"], "Beta")
        check("and so is the group holding it",
              detail["clashes"][0]["group_name"], "Morning banks")

        async with AsyncSessionLocal() as db:
            groups = (await db.execute(select(ScheduleGroup))).scalars().all()
        check("nothing was half created", len(groups), 1)

        r = await c.get("/api/v1/schedules/site-availability", headers=admin)
        taken = {row["site_name"]: row["group_name"] for row in r.json()}
        check("picker marks Alpha as taken", taken["Alpha"], "Morning banks")
        check("and leaves Gamma free", taken["Gamma"], None)

        print("\n=== a second group over free sites ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "site_ids": [ids["gamma"]], "frequency": "custom",
            "run_at": "09:30:00", "interval_days": 3})
        check("created", r.status_code, 201)
        second = r.json()
        check("interval stored", second["interval_days"], 3)
        r = await c.get("/api/v1/schedules", headers=admin)
        check("both listed", len(r.json()), 2)
        check("newest first", r.json()[0]["id"], second["id"])

        print("\n=== editing ===")
        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=staff,
                          json={"run_at": "07:00:00"})
        check("editing needs the permission", r.status_code, 403)

        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"frequency": "weekly", "run_at": "07:00:00"})
        check("timing changed", r.json()["frequency"], "weekly")
        check("next run recalculated",
              as_utc(datetime.fromisoformat(r.json()["next_run_at"]))
              > datetime.now(timezone.utc), True)

        r = await c.patch(f"/api/v1/schedules/{second['id']}", headers=admin,
                          json={"frequency": "daily"})
        check("switching off custom clears the interval",
              r.json()["interval_days"], None)

        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"site_ids": [ids["gamma"]]})
        check("cannot steal another group's site", r.status_code, 409)

        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"site_ids": [ids["alpha"]]})
        check("dropping a site is allowed", len(r.json()["sites"]), 1)
        r = await c.get("/api/v1/schedules/site-availability", headers=admin)
        freed = {row["site_name"]: row["group_id"] for row in r.json()}
        check("the dropped site is free again", freed["Beta"], None)

        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin, json={})
        check("an empty edit is rejected", r.status_code, 400)
        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"site_ids": []})
        check("removing every site is rejected", r.status_code, 422)

        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"enabled": False})
        check("disabling clears the next run", r.json()["next_run_at"], None)
        r = await c.patch(f"/api/v1/schedules/{first['id']}", headers=admin,
                          json={"enabled": True})
        check("re-enabling restores it", r.json()["next_run_at"] is not None, True)

        print("\n=== running what is due ===")
        check("nothing runs early", await scheduler.run_due(), 0)

        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, second["id"])
            group.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()
            was_due = group.next_run_at

        fake.calls.clear()
        check("the due group runs", await scheduler.run_due(), 1)
        check("its site was scraped", any("gamma.test" in u for u in fake.calls), True)
        check("other groups were left alone",
              any("alpha.test" in u for u in fake.calls), False)

        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, second["id"])
            check("next run moved forward",
                  as_utc(group.next_run_at) > as_utc(was_due), True)
            check("outcome recorded", group.last_status, "ok")
            tenders = (await db.execute(select(Tender))).scalars().all()
        check("a tender was stored", len(tenders) >= 1, True)
        check("nothing is due immediately after", await scheduler.run_due(), 0)

        print("\n=== a group cannot fire twice ===")
        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, second["id"])
            group.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()
        results = await asyncio.gather(scheduler.run_due(), scheduler.run_due())
        check("only one runner claims it", sorted(results), [0, 1])

        print("\n=== a group of only paused sites is skipped ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "name": "Paused only", "site_ids": [ids["paused"]],
            "frequency": "daily", "run_at": "08:00:00"})
        paused_group = r.json()["id"]
        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, paused_group)
            group.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()
        fake.calls.clear()
        check("it is claimed", await scheduler.run_due(), 1)
        check("but nothing is fetched", fake.calls, [])
        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, paused_group)
            check("and the reason is recorded", group.last_status, "skipped")

        print("\n=== a failing site is recorded, not fatal ===")
        r = await c.post("/api/v1/schedules", headers=admin, json={
            "name": "Mixed", "site_ids": [ids["broken"], ids["beta"]],
            "frequency": "daily", "run_at": "08:00:00"})
        mixed = r.json()["id"]
        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, mixed)
            group.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.commit()

        fake.calls.clear()
        check("it runs", await scheduler.run_due(), 1)
        check("the healthy site was still scraped",
              any("beta.test" in u for u in fake.calls), True)
        async with AsyncSessionLocal() as db:
            group = await db.get(ScheduleGroup, mixed)
            check("failure recorded", group.last_status, "failed")
            check("reason recorded", "outage" in (group.last_error or ""), True)
            check("and it is rescheduled anyway",
                  as_utc(group.next_run_at) > datetime.now(timezone.utc), True)

        print("\n=== deleting ===")
        r = await c.delete(f"/api/v1/schedules/{first['id']}", headers=staff)
        check("deleting needs the permission", r.status_code, 403)
        r = await c.delete(f"/api/v1/schedules/{first['id']}", headers=admin)
        check("deleted", r.status_code, 204)
        r = await c.delete(f"/api/v1/schedules/{first['id']}", headers=admin)
        check("deleting twice is a 404", r.status_code, 404)

        r = await c.get("/api/v1/schedules/site-availability", headers=admin)
        freed = {row["site_name"]: row["group_id"] for row in r.json()}
        check("its sites are free again", freed["Alpha"], None)
        async with AsyncSessionLocal() as db:
            site = await db.get(Site, ids["alpha"])
        check("the site itself survives", site is not None, True)

        r = await c.get("/api/v1/schedules/9999", headers=admin)
        check("missing schedule is a 404", r.status_code, 404)

    await engine.dispose()
    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        raise SystemExit(1)
    print("ALL SCHEDULE CHECKS PASSED")


asyncio.run(main())

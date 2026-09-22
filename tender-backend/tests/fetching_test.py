"""Tests for the Firecrawl client and pagination detection.

Firecrawl is mocked, so this makes no network calls and costs no credits.

Run with:  PYTHONPATH=. python tests/fetching_test.py
"""

import asyncio

import httpx

from app.ingestion.firecrawl import FirecrawlClient, FirecrawlError
from app.ingestion.pagination import build_next_url, find_next_page

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


NAV = """<html><body><table>rows</table>
<ul class="pagination">
  <li><a href="?page=1">1</a></li>
  <li><a href="?page=2">2</a></li>
  <li><a href="?page=3">3</a></li>
</ul></body></html>"""


def test_pagination():
    print("=== next page URL ===")
    check("appends page param", build_next_url("https://x.test/n", 2), "https://x.test/n?page=2")
    check("keeps existing query", build_next_url("https://x.test/n?type=18", 2),
          "https://x.test/n?type=18&page=2")
    check("replaces existing page", build_next_url("https://x.test/n?page=1", 3),
          "https://x.test/n?page=3")

    print("\n=== pagination detection ===")
    check("finds page 2", find_next_page(NAV, current_page=1, base_url="https://x.test/n", max_pages=5),
          (2, "https://x.test/n?page=2"))
    check("stops on last page",
          find_next_page(NAV, current_page=3, base_url="https://x.test/n", max_pages=5), None)
    check("honours the page cap",
          find_next_page(NAV, current_page=5, base_url="https://x.test/n", max_pages=5), None)
    check("no pagination block",
          find_next_page("<p>one page only</p>", current_page=1,
                         base_url="https://x.test/n", max_pages=5), None)
    check("bengali numerals",
          find_next_page('<div class="pagination"><a href="?page=২">২</a></div>',
                         current_page=1, base_url="https://x.test/n", max_pages=5),
          (2, "https://x.test/n?page=2"))
    check("ignores page numbers outside the nav",
          find_next_page(
              '<a href="/article?page=99">x</a><ul class="pagination"><a href="?page=2">2</a></ul>',
              current_page=1, base_url="https://x.test/n", max_pages=5),
          (2, "https://x.test/n?page=2"))
    check("ignores absurd page numbers",
          find_next_page('<div class="pagination"><a href="?page=5000">x</a></div>',
                         current_page=1, base_url="https://x.test/n", max_pages=5), None)


async def test_client():
    print("\n=== firecrawl client (mocked) ===")
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        body = request.read().decode()
        if "success.test" in body:
            return httpx.Response(200, json={"data": {"rawHtml": "<html>ok</html>"}})
        if "flaky.test" in body:
            if attempts["n"] < 3:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"data": {"rawHtml": "<html>recovered</html>"}})
        if "badkey.test" in body:
            return httpx.Response(401)
        if "empty.test" in body:
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def make():
        c = FirecrawlClient("fc-test", max_retries=3, delay_between_s=0)
        c._client = httpx.AsyncClient(transport=transport)
        return c

    client = make()
    check("returns raw html", await client.scrape("https://success.test/t"), "<html>ok</html>")
    await client.aclose()

    attempts["n"] = 0
    client = make()
    check("retries transient errors", await client.scrape("https://flaky.test/t"),
          "<html>recovered</html>")
    check("took three attempts", attempts["n"], 3)
    await client.aclose()

    client = make()
    try:
        await client.scrape("https://badkey.test/t")
        check("bad key raises", False, True)
    except FirecrawlError:
        check("bad key raises", True, True)
    await client.aclose()

    client = make()
    try:
        await client.scrape("https://empty.test/t")
        check("empty html raises", False, True)
    except FirecrawlError:
        check("empty html raises", True, True)
    await client.aclose()

    try:
        FirecrawlClient("")
        check("missing key rejected", False, True)
    except ValueError:
        check("missing key rejected", True, True)

    # Concurrency cap
    state = {"active": 0, "peak": 0}

    async def slow(request):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return httpx.Response(200, json={"data": {"rawHtml": "<i>x</i>"}})

    client = FirecrawlClient("fc-test", max_concurrent=2, delay_between_s=0)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
    await asyncio.gather(*(client.scrape(f"https://x.test/{i}") for i in range(6)))
    check("respects the concurrency cap", state["peak"] <= 2, True)
    await client.aclose()


test_pagination()
asyncio.run(test_client())

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    raise SystemExit(1)
print("ALL FETCHING CHECKS PASSED")
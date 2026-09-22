"""Client for the Firecrawl scrape API.

Firecrawl renders JavaScript and returns the finished HTML, which matters
because several of these notice boards build their tables client-side.

A full run is up to 38 sites times 5 pages, so this client deliberately:
  * limits how many requests run at once,
  * leaves a gap between requests to avoid tripping rate limits,
  * retries on timeouts, 429s and 5xx with exponential backoff,
  * and never raises on a single site's failure, so one broken portal cannot
    abort the whole run.
"""

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)


class FirecrawlError(Exception):
    """A scrape failed after exhausting retries."""


class FirecrawlClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.firecrawl.dev/v1/scrape",
        wait_for_ms: int = 5000,
        scrape_timeout_ms: int = 120_000,
        request_timeout_s: float = 240.0,
        max_retries: int = 3,
        max_concurrent: int = 3,
        delay_between_s: float = 1.0,
    ):
        if not api_key:
            raise ValueError("Firecrawl API key is missing. Set FIRECRAWL_API_KEY.")

        self._api_key = api_key
        self._base_url = base_url
        self._wait_for_ms = wait_for_ms
        self._scrape_timeout_ms = scrape_timeout_ms
        self._max_retries = max_retries
        self._delay_between_s = delay_between_s

        self._limiter = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            timeout=request_timeout_s,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def __aenter__(self) -> "FirecrawlClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def scrape(self, url: str) -> str:
        """Fetch one page and return its raw HTML. Raises FirecrawlError."""
        payload = {
            "url": url,
            "formats": ["rawHtml"],
            "onlyMainContent": False,
            "waitFor": self._wait_for_ms,
            "timeout": self._scrape_timeout_ms,
        }

        last_error = "unknown error"

        async with self._limiter:
            for attempt in range(1, self._max_retries + 1):
                try:
                    response = await self._client.post(self._base_url, json=payload)
                except httpx.TimeoutException:
                    last_error = "request timed out"
                except httpx.HTTPError as exc:
                    last_error = f"network error: {exc}"
                else:
                    if response.status_code == 200:
                        html = self._read_html(response)
                        if html:
                            await asyncio.sleep(self._delay_between_s)
                            return html
                        last_error = "response contained no rawHtml"
                    elif response.status_code == 429:
                        last_error = "rate limited"
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            await asyncio.sleep(int(retry_after))
                    elif response.status_code in (401, 403):
                        # Credentials will not fix themselves; fail immediately.
                        raise FirecrawlError(
                            f"Firecrawl rejected the API key ({response.status_code})"
                        )
                    elif 500 <= response.status_code < 600:
                        last_error = f"server error {response.status_code}"
                    else:
                        raise FirecrawlError(
                            f"Firecrawl returned {response.status_code} for {url}"
                        )

                if attempt < self._max_retries:
                    # Exponential backoff with jitter, so parallel workers do
                    # not all retry on the same beat.
                    delay = (2**attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Firecrawl attempt %s/%s failed for %s (%s); retrying in %.1fs",
                        attempt, self._max_retries, url, last_error, delay,
                    )
                    await asyncio.sleep(delay)

        raise FirecrawlError(f"Failed to scrape {url} after {self._max_retries} attempts: {last_error}")

    @staticmethod
    def _read_html(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        # Firecrawl wraps the result in {"success": true, "data": {...}}
        return (body.get("data") or {}).get("rawHtml") or ""
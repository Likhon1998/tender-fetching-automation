"""Working out whether a notice board has another page.

Ported from the n8n workflow. The approach is deliberately crude but robust
across 38 differently-built sites: find every page number referenced in the
pagination area, and if the highest one is above the current page, there is
more to fetch.

Restricting the search to the pagination region matters. Page numbers appear
inside article URLs and query strings all over these pages, and scanning the
whole document would invent pages that do not exist.
"""

import re

from app.ingestion.dates import bengali_digits_to_ascii

# Blocks that usually hold the page links.
_REGION_PATTERNS = [
    re.compile(
        r'<(?:nav|ul|div)[^>]*class="[^"]*paginat[^"]*"[^>]*>.*?</(?:nav|ul|div)>',
        re.I | re.S,
    ),
    re.compile(r'<ul[^>]*class="[^"]*page[^"]*"[^>]*>.*?</ul>', re.I | re.S),
    re.compile(r'<div[^>]*class="[^"]*pager[^"]*"[^>]*>.*?</div>', re.I | re.S),
    re.compile(r'<nav[^>]*aria-label="[^"]*[Pp]aginat[^"]*"[^>]*>.*?</nav>', re.I | re.S),
    re.compile(r'<div[^>]*id="[^"]*paginat[^"]*"[^>]*>.*?</div>', re.I | re.S),
]

# Ways these sites express a page number in a link.
_PAGE_NUMBER_PATTERNS = [
    re.compile(r"[?&]page=(\d+)", re.I),
    re.compile(r"[?&]p=(\d+)", re.I),
    re.compile(r"[?&]pageNo=(\d+)", re.I),
    re.compile(r"[?&]pg=(\d+)", re.I),
    re.compile(r"/page/(\d+)", re.I),
]

_EXISTING_PAGE_PARAM = re.compile(r"([?&]page=)\d+", re.I)

# How much of the tail to fall back on when no pagination block is recognised.
_TAIL_LENGTH = 6000


def extract_pagination_region(html: str) -> str:
    """Narrow the HTML down to the part likely to hold page links."""
    parts = []
    for pattern in _REGION_PATTERNS:
        parts.extend(pattern.findall(html))
    if parts:
        return "\n".join(parts)
    # Pagination is nearly always at the bottom of the page.
    return html[-_TAIL_LENGTH:]


def build_next_url(base_url: str, next_page: int) -> str:
    """Point a URL at a given page, replacing any page parameter already there."""
    if re.search(r"[?&]page=\d+", base_url, re.I):
        return _EXISTING_PAGE_PARAM.sub(rf"\g<1>{next_page}", base_url, count=1)
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={next_page}"


def find_next_page(
    html: str, *, current_page: int, base_url: str, max_pages: int
) -> tuple[int, str] | None:
    """Return (next page number, URL) or None when there is nothing more.

    Stops at max_pages regardless of what the site advertises, so a portal
    with a thousand pages cannot stall an entire run.
    """
    if current_page >= max_pages:
        return None

    region = extract_pagination_region(bengali_digits_to_ascii(html))

    numbers: set[int] = set()
    for pattern in _PAGE_NUMBER_PATTERNS:
        for match in pattern.finditer(region):
            value = int(match.group(1))
            # Ignore absurd values; they are almost always ids, not pages.
            if 0 < value < 1000:
                numbers.add(value)

    if not numbers or max(numbers) <= current_page:
        return None

    next_page = current_page + 1
    return next_page, build_next_url(base_url, next_page)
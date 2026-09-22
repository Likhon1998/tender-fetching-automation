"""Small HTML helpers shared by the site parsers.

These use regular expressions rather than a DOM parser, matching the original
n8n implementation. That is unusual, but deliberate: the parsers were tuned by
hand against the real markup of 38 specific sites, and a faithful port keeps
that hard-won behaviour intact. Swapping in a DOM parser would silently change
what each strategy matches.
"""

import html as html_module
import re
from urllib.parse import urljoin

_TAG = re.compile(r"<[^>]+>")
_NUMERIC_ENTITY = re.compile(r"&#(\d+);")
_NAMED_ENTITY = re.compile(r"&[a-z]+;", re.I)
_WHITESPACE = re.compile(r"\s+")

_HREF_PDF = re.compile(r'href="([^"]*\.pdf[^"]*)"', re.I)
_HREF_ABSOLUTE = re.compile(r'href="(https?[^"]+)"', re.I)
_HREF_RELATIVE = re.compile(r'href="([^"#javascript][^"]*)"', re.I)

_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
_TD_COUNT = re.compile(r"<td[\s>]", re.I)
_TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)

# Titles that are really serial numbers or bare dates.
_ONLY_DIGITS = re.compile(r"^[\d০-৯\s]+$")
_JUNK_DATE_PATTERNS = [
    re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$"),
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"),
    re.compile(r"^\d{1,2}[-\s][A-Za-z]{3,9}[-\s,]+\d{4}$"),
]


def strip_tags(fragment: str | None) -> str:
    """Turn an HTML fragment into plain collapsed text."""
    if not fragment:
        return ""
    text = _TAG.sub(" ", fragment)
    text = text.replace("&nbsp;", " ").replace("&NBSP;", " ")
    text = html_module.unescape(text)
    text = _NUMERIC_ENTITY.sub(lambda m: chr(int(m.group(1))), text)
    text = _NAMED_ENTITY.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def find_pdf_link(fragment: str) -> str:
    m = _HREF_PDF.search(fragment or "")
    return m.group(1) if m else ""


def find_absolute_link(fragment: str) -> str:
    m = _HREF_ABSOLUTE.search(fragment or "")
    return m.group(1) if m else ""


def find_relative_link(fragment: str) -> str:
    m = _HREF_RELATIVE.search(fragment or "")
    return m.group(1).strip() if m else ""


def absolute_url(url: str, base: str) -> str:
    """Resolve a possibly relative href against the page it came from."""
    if not url:
        return ""
    if url.startswith("http"):
        return url
    try:
        return urljoin(base, url)
    except ValueError:
        return url


def looks_like_junk_title(title: str) -> bool:
    """True for cells that are serial numbers, bare dates, or too short."""
    if not title or len(title) < 3:
        return True
    if _ONLY_DIGITS.match(title):
        return True
    return any(p.match(title) for p in _JUNK_DATE_PATTERNS)


def extract_rows(table_html: str) -> list[str]:
    return _TR.findall(table_html or "")


def extract_cells(row_html: str) -> list[str]:
    return _TD.findall(row_html or "")


def pick_best_table(html: str, min_cols: int) -> list[str]:
    """Return the data rows of the largest table with enough columns.

    These pages often contain several tables used for layout, so the biggest
    one with the expected shape is the notice table.
    """
    best: list[str] = []
    for table_html in _TABLE.findall(html or ""):
        data_rows = [
            row
            for row in extract_rows(table_html)
            if len(_TD_COUNT.findall(row)) >= min_cols
        ]
        if len(data_rows) > len(best):
            best = data_rows
    return best

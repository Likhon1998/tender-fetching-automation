"""Date parsing for scraped notices.

Ported from the production n8n workflow. These sites publish dates in a dozen
inconsistent formats, some using Bengali numerals, so parsing is deliberately
forgiving: anything unrecognised keeps its raw text and yields no ISO date
rather than guessing.
"""

import re
from datetime import date

# Bengali numerals to ASCII, so "০৪-ডিসেম্বর-২০২৬" can be read.
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Patterns that carry a full day + month + year, used for the cutoff check.
_FULL_DATE_PATTERNS = [
    re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"),            # 2026-12-04
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),            # 04-12-2026
    re.compile(r"\b(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/,\s]+(\d{4})\b"),  # 04-Dec-2026
    re.compile(r"\b([A-Za-z]{3,9})[-/\s]+(\d{1,2})[-/,\s]+(\d{4})\b"), # Dec 4, 2026
]

_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_DD_MON_YYYY = re.compile(r"^(\d{1,2})[-/.\s]([A-Za-z]{3,9})[-/.,\s]+(\d{4})$")
_MON_DD_YYYY = re.compile(r"^([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})$")
_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_BARE_YEAR = re.compile(r"^\d{4}$")


def bengali_digits_to_ascii(text: str | None) -> str:
    return (text or "").translate(_BENGALI_DIGITS)


def _build(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None  # e.g. 31 February


def normalise_date(raw: str | None) -> tuple[date | None, str]:
    """Return (parsed date or None, the cleaned original string)."""
    text = bengali_digits_to_ascii(raw).strip()
    if not text:
        return None, ""

    if _BARE_YEAR.match(text):
        return None, text  # a year alone is not a date

    if m := _ISO.match(text):
        return _build(int(m[1]), int(m[2]), int(m[3])), text

    if m := _DD_MON_YYYY.match(text):
        month = _MONTHS.get(m[2].lower()[:3])
        if month:
            return _build(int(m[3]), month, int(m[1])), text

    if m := _MON_DD_YYYY.match(text):
        month = _MONTHS.get(m[1].lower()[:3])
        if month:
            return _build(int(m[3]), month, int(m[2])), text

    if m := _NUMERIC.match(text):
        a, b, year = int(m[1]), int(m[2]), int(m[3])
        # Decide day-first vs month-first from whichever value cannot be a
        # month. Genuinely ambiguous dates default to day-first, which is the
        # regional convention.
        if a > 12:
            day, month = a, b
        elif b > 12:
            day, month = b, a
        else:
            day, month = a, b
        return _build(year, month, day), text

    return None, text


def is_within_cutoff(raw: str | None, cutoff_year: int) -> bool:
    """True if the notice is recent enough to be worth showing.

    Undated notices and bare years count as recent: a missing date means the
    source published none, not that the notice is old.
    """
    text = bengali_digits_to_ascii(raw).strip()
    if not text:
        return True

    for pattern in _FULL_DATE_PATTERNS:
        if m := pattern.search(text):
            for group in m.groups():
                if group and re.fullmatch(r"\d{4}", group):
                    return int(group) >= cutoff_year

    return True


# Many notices state their deadline inside the title, in phrasings like
# "Date of submission: on or before August 30, 2026" or "Last date 15-06-2026".
# Sites that publish a separate submission column are rare, so reading the
# title is the main way to learn a deadline.
_DEADLINE_CUES = re.compile(
    r"(?:on or before|last date(?:\s+of\s+submission)?|deadline|closing date"
    r"|submission (?:date|deadline)|due (?:on|date)|bid closing)"
    r"[^\dA-Za-z]{0,15}"
    r"([A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4}"
    r"|\d{1,2}[-/.\s][A-Za-z]{3,9}[-/.,\s]+\d{4}"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
    r"|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
    re.I,
)


def find_deadline(text: str | None) -> tuple[date | None, str]:
    """Pull a submission deadline out of a notice title.

    Returns (parsed date or None, the matched text). Anything unrecognised
    yields no date rather than a guess.
    """
    cleaned = bengali_digits_to_ascii(text).strip()
    if not cleaned:
        return None, ""

    match = _DEADLINE_CUES.search(cleaned)
    if not match:
        return None, ""

    raw = match.group(1).strip().rstrip(",")
    parsed, _ = normalise_date(raw)
    return parsed, raw

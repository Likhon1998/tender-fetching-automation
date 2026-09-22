"""Per-site parsers for the tender notice boards.

Each site's HTML is laid out differently, so every site is assigned a named
strategy. Most fall into two shared families:

  * ``data-column``  five government portals built on the national portal
                     template, which tags cells with data-column attributes
  * ``positional``   plain tables, where each site declares which column
                     index holds the date, title and link

The rest are one-off layouts (cards, accordions, list items) that needed
their own handling. All of it is ported from the production n8n workflow,
where the selectors were tuned against the real pages.

Adding a site means adding an entry to SITE_STRATEGIES. A site with no entry
is skipped rather than guessed at, so a misconfigured site produces nothing
instead of nonsense.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from app.ingestion.dates import bengali_digits_to_ascii, normalise_date
from app.ingestion.html_utils import (
    absolute_url,
    extract_cells,
    find_absolute_link,
    find_pdf_link,
    find_relative_link,
    looks_like_junk_title,
    pick_best_table,
    strip_tags,
)


# What the date on a listing page means. Most sites show when a notice was
# published; a few show the submission deadline instead. Storing which one it
# is lets the interface label it correctly instead of guessing.
PUBLISH_DATE = "publish"
SUBMISSION_DATE = "submission"


@dataclass(frozen=True)
class ParsedNotice:
    title: str
    date_raw: str
    pdf_link: str
    date_type: str = PUBLISH_DATE
    # Some listings carry a deadline in a column of its own, separate from
    # the publish date. Where they do, it is read here rather than being
    # guessed at from the title.
    submission_raw: str = ""


@dataclass(frozen=True)
class PositionalColumns:
    """Zero-based column indexes for a plain table.

    `date` is the publish date. A few sites show the submission deadline in a
    second column; `submission` points at it where that is the case.
    """

    title: int
    link: int | None = None
    date: int | None = None
    submission: int | None = None
    min_cols: int = 2


# ── Site to strategy mapping ──────────────────────────────────────────────
SITE_STRATEGIES: dict[str, str] = {
    # Bangladesh National Portal template
    "MoEdu": "data-column",
    "LGD": "data-column",
    "RTHD": "data-column",
    "DPE": "data-column",
    "SPARRSO": "data-column",
    # One-off layouts
    "CityBank": "citybank-list",
    "MTB": "mtb-list",
    "HEAT_UGC": "heat-cards",
    "Grameenphone": "gp-cards",
    "TBL": "tbl-cards",
    "IDLC": "idlc-cards",
    "ICDDRB": "icddrb-cards",
    "StandardBank": "standardbank-cards",
    "DBBL": "dbbl-cards",
    "IFIC": "ific-panels",
    "MetLife": "metlife-cards",
    # Plain tables
    "Navy": "positional",
    "BracBank": "positional",
    "EBL": "positional",
    "ModhumotiBank": "positional",
    "BGCB": "positional",
    "JamunaBank": "positional",
    "MeghnaBank": "positional",
    "MidlandBank": "positional",
    "MercantileBank": "positional",
    "NationalBank": "positional",
    "PubaliBank": "positional",
    "UttaraBank": "positional",
    "BankAsia": "positional",
    "CommunityBank": "positional",
    "OneBank": "positional",
    "RupaliBank": "positional",
    "BangladeshBank": "positional",
    "UCB": "positional",
    "PrimeBank": "positional",
    "BCPS": "positional",
    "IslamiBank": "positional",
    "PKSF": "positional",
}

# Column layouts for the positional sites, as observed on each page.
POSITIONAL_COLUMNS: dict[str, PositionalColumns] = {
    "Navy": PositionalColumns(title=1, link=6, date=4, min_cols=7),
    "BracBank": PositionalColumns(title=1, link=2, date=None, min_cols=3),
    "EBL": PositionalColumns(title=1, link=2, date=0, min_cols=3),
    "ModhumotiBank": PositionalColumns(title=2, link=3, date=0, min_cols=4),
    "BGCB": PositionalColumns(title=3, link=4, date=1, min_cols=5),
    "JamunaBank": PositionalColumns(title=0, link=1, date=None, min_cols=2),
    "MeghnaBank": PositionalColumns(title=1, link=2, date=0, min_cols=3),
    "MidlandBank": PositionalColumns(title=1, link=1, date=2, min_cols=4),
    "MercantileBank": PositionalColumns(title=2, link=3, date=1, min_cols=4),
    "NationalBank": PositionalColumns(title=3, link=4, date=1, min_cols=5),
    "PubaliBank": PositionalColumns(title=1, link=3, date=2, min_cols=4),
    "UttaraBank": PositionalColumns(title=0, link=2, date=1, min_cols=3),
    "BankAsia": PositionalColumns(title=1, link=4, date=2, min_cols=5),
    "CommunityBank": PositionalColumns(title=1, link=5, date=2, min_cols=6),
    "OneBank": PositionalColumns(title=0, link=1, date=None, min_cols=2),
    "RupaliBank": PositionalColumns(title=1, link=1, date=3, min_cols=4),
    "BangladeshBank": PositionalColumns(title=3, link=3, date=1, submission=2, min_cols=4),
    "UCB": PositionalColumns(title=1, link=3, date=None, min_cols=4),
    "PrimeBank": PositionalColumns(title=3, link=4, date=1, min_cols=5),
    "BCPS": PositionalColumns(title=2, link=3, date=0, min_cols=4),
    "IslamiBank": PositionalColumns(title=1, link=3, date=2, min_cols=4),
    "PKSF": PositionalColumns(title=2, link=5, date=3, min_cols=6),
}

# Below this length the page is almost certainly an error or a redirect.
MIN_USABLE_HTML = 200


def _detect_deadline(cells: list[str], columns: "PositionalColumns", published) -> str:
    """Find a submission deadline in a row that has more than one date column.

    Several notice boards list the publish date and the deadline side by side,
    and configuring each one by hand would mean checking all 38 sites and
    rechecking whenever a layout changes. Instead: a deadline is a date in the
    same row that falls after the publish date. The latest such date wins,
    since a row occasionally carries an opening date too.

    Columns already spoken for are skipped, and a row with no usable publish
    date is left alone rather than guessed at.
    """
    if published is None:
        return ""

    spoken_for = {columns.title, columns.link, columns.date}
    best_raw, best_date = "", None

    for index, cell in enumerate(cells):
        if index in spoken_for:
            continue
        text = bengali_digits_to_ascii(strip_tags(cell)).strip()
        if not text or len(text) > 40:
            continue
        parsed, raw = normalise_date(text)
        if parsed is None or parsed <= published:
            continue
        if best_date is None or parsed > best_date:
            best_raw, best_date = raw, parsed

    return best_raw


# ── Shared strategies ─────────────────────────────────────────────────────

_TBODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.I | re.S)
_PORTAL_ROW = re.compile(r'<tr[^>]*class="table-tr"[^>]*>(.*?)</tr>', re.I | re.S)
_HAS_TH = re.compile(r"<th[\s>]", re.I)


def _column_text(row_html: str, column: str) -> str:
    pattern = re.compile(
        rf'<td[^>]*data-column="{column}"[^>]*>(.*?)</td>', re.I | re.S
    )
    m = pattern.search(row_html)
    return strip_tags(m.group(1)) if m else ""


def _column_href(row_html: str, column: str) -> str:
    pattern = re.compile(
        rf'<td[^>]*data-column="{column}"[^>]*>.*?href="([^"]+)"', re.I | re.S
    )
    m = pattern.search(row_html)
    return m.group(1).strip() if m else ""


def parse_data_column(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """Government portals that tag each cell with a data-column attribute."""
    tbody_match = _TBODY.search(html)
    body = tbody_match.group(1) if tbody_match else html

    notices = []
    for match in _PORTAL_ROW.finditer(body):
        row_html = match.group(1)
        if _HAS_TH.search(row_html):
            continue
        if re.search(r"column-input", row_html, re.I):
            continue
        if re.search(r"toggle-hidden", match.group(0), re.I):
            continue

        title = _column_text(row_html, "title")
        if looks_like_junk_title(title):
            continue

        date_raw = bengali_digits_to_ascii(_column_text(row_html, "publish_date"))
        # The portal template names its deadline column inconsistently, so
        # try the ones seen in the wild before falling back to the title.
        submission_raw = ""
        for column in ("deadline", "last_date", "submission_date", "expire_date"):
            submission_raw = bengali_digits_to_ascii(_column_text(row_html, column))
            if submission_raw:
                break
        link = (
            _column_href(row_html, "files")
            or find_pdf_link(row_html)
            or find_absolute_link(row_html)
        )
        notices.append(
            ParsedNotice(
                title,
                date_raw,
                absolute_url(link, source_url),
                submission_raw=submission_raw,
            )
        )
    return notices


def parse_positional(
    html: str, source_url: str, columns: PositionalColumns | None = None, **_
) -> list[ParsedNotice]:
    """Plain tables where each site declares its own column order."""
    if columns is None:
        return []

    notices = []
    for row_html in pick_best_table(html, columns.min_cols):
        cells = extract_cells(row_html)
        if len(cells) < columns.min_cols:
            continue

        title = strip_tags(cells[columns.title]) if columns.title < len(cells) else ""
        if looks_like_junk_title(title):
            continue

        date_raw = ""
        if columns.date is not None and columns.date < len(cells):
            date_raw = bengali_digits_to_ascii(strip_tags(cells[columns.date]))

        submission_raw = ""
        if columns.submission is not None and columns.submission < len(cells):
            submission_raw = bengali_digits_to_ascii(
                strip_tags(cells[columns.submission])
            )
        elif date_raw:
            # No deadline column configured, so look for one: any later date
            # in the same row is almost certainly the submission deadline.
            published, _ = normalise_date(date_raw)
            submission_raw = _detect_deadline(cells, columns, published)

        link = ""
        if columns.link is not None and columns.link < len(cells):
            cell = cells[columns.link]
            link = find_pdf_link(cell) or find_absolute_link(cell) or find_relative_link(cell)
        # Fall back to scanning every cell: some rows put the download
        # elsewhere, and a notice without a link is still worth keeping.
        if not link:
            for cell in cells:
                link = find_pdf_link(cell)
                if link:
                    break
        if not link:
            for cell in cells:
                link = find_absolute_link(cell)
                if link:
                    break

        notices.append(
            ParsedNotice(
                title,
                date_raw,
                absolute_url(link, source_url),
                submission_raw=submission_raw,
            )
        )
    return notices


# ── One-off site layouts ──────────────────────────────────────────────────

_CITYBANK_ROW = re.compile(
    r'<div[^>]*class="[^"]*wt-20-16p-title[^"]*"[^>]*>(.*?)</div>\s*</div>', re.I | re.S
)
_FIRST_DIV = re.compile(r"<div[^>]*>(.*?)</div>", re.I | re.S)
_ON_OR_BEFORE = re.compile(
    r"(?:on or before|before)\s+([A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})", re.I
)


def parse_citybank_list(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """City Bank puts the deadline inside the title text and offers no link."""
    notices = []
    for match in _CITYBANK_ROW.finditer(html):
        row_html = match.group(1)
        inner = _FIRST_DIV.search(row_html)
        text = strip_tags(inner.group(1)) if inner else strip_tags(row_html)
        if looks_like_junk_title(text):
            continue

        date_match = _ON_OR_BEFORE.search(text)
        notices.append(
            ParsedNotice(
                text,
                date_match.group(1) if date_match else "",
                "",
                date_type=SUBMISSION_DATE,
            )
        )
    return notices


_MTB_ROW = re.compile(
    r'<div class="date-box">(.*?)</div>\s*<div class="content-box">(.*?)</div>\s*</li>',
    re.I | re.S,
)
_MTB_MONTH = re.compile(r'<span[^>]*class="month"[^>]*>(.*?)</span>', re.I | re.S)
_MTB_DAY = re.compile(r'<h1[^>]*class="day"[^>]*>(.*?)</h1>', re.I | re.S)
_MTB_TITLE = re.compile(
    r'<span[^>]*class="press-head"[^>]*>.*?<a[^>]*>(.*?)</a>', re.I | re.S
)
_MTB_LINK = re.compile(r'<a[^>]*class="press-read-more"[^>]*href="([^"]+)"', re.I)


def parse_mtb_list(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """MTB shows month and day but no year, so the current year is assumed."""
    year = datetime.now().year
    notices = []
    for match in _MTB_ROW.finditer(html):
        date_box, content_box = match.group(1), match.group(2)

        month_m = _MTB_MONTH.search(date_box)
        day_m = _MTB_DAY.search(date_box)
        month = strip_tags(month_m.group(1)) if month_m else ""
        day = strip_tags(day_m.group(1)) if day_m else ""
        date_raw = f"{month} {day}, {year}" if month and day else ""

        title_m = _MTB_TITLE.search(content_box)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue

        link_m = _MTB_LINK.search(content_box)
        link = absolute_url(link_m.group(1), source_url) if link_m else ""
        notices.append(ParsedNotice(title, date_raw, link))
    return notices


_HEAT_MARKER = "overflow-hidden rounded-lg border border-gray-100 bg-white shadow-sm"
_HEAT_DATE = re.compile(r"<div[^>]*text-green-600[^>]*>(.*?)</div>", re.I | re.S)
_HEAT_TITLE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.I | re.S)
_HEAT_PDF = [
    re.compile(r'<a[^>]*href="([^"]+\.pdf[^"]*)"[^>]*download', re.I),
    re.compile(r'<a[^>]*download[^>]*href="([^"]+\.pdf[^"]*)"', re.I),
]


def parse_heat_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """HEAT/UGC cards. The green badge is the publish date; the orange one is
    the deadline, so only the green one is read."""
    card_pattern = re.compile(
        rf'<div class="{re.escape(_HEAT_MARKER)}.*?(?=<div class="{re.escape(_HEAT_MARKER)}|$)',
        re.I | re.S,
    )
    notices = []
    for match in card_pattern.finditer(html):
        card = match.group(0)

        date_m = _HEAT_DATE.search(card)
        title_m = _HEAT_TITLE.search(card)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue

        link = ""
        for pattern in _HEAT_PDF:
            if m := pattern.search(card):
                link = absolute_url(m.group(1), source_url)
                break

        notices.append(
            ParsedNotice(title, strip_tags(date_m.group(1)) if date_m else "", link)
        )
    return notices


_GP_CARD = re.compile(r'<div class="css-q000kp">(.*?)</div>\s*</div>\s*</a>\s*</div>', re.I | re.S)
_GP_MONTH = re.compile(r"<p[^>]*>([A-Za-z]{3})</p>", re.I)
_GP_DAY = re.compile(r"<p[^>]*>(\d{1,2})</p>", re.I)
_GP_TITLE = re.compile(r'<div class="css-0"[^>]*>(.*?)</div>', re.I | re.S)
_ANY_HREF = re.compile(r'href="([^"]+)"', re.I)


def parse_gp_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """Grameenphone cards: Bengali titles, month and day but no year."""
    year = datetime.now().year
    notices = []
    for match in _GP_CARD.finditer(html):
        card = match.group(1)

        month_m = _GP_MONTH.search(card)
        day_m = _GP_DAY.search(card)
        month = strip_tags(month_m.group(1)) if month_m else ""
        day = strip_tags(day_m.group(1)) if day_m else ""
        date_raw = f"{month} {day}, {year}" if month and day else ""

        title_m = _GP_TITLE.search(card)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue

        link_m = _ANY_HREF.search(card)
        link = absolute_url(link_m.group(1), source_url) if link_m else ""
        notices.append(ParsedNotice(title, date_raw, link))
    return notices


_TBL_CARD = re.compile(r'<div class="col-md-4 col-sm-6 views-row">(.*?)</div>\s*</div>', re.I | re.S)
_TBL_TITLE = re.compile(
    r'<div class="views-field-title"><h2><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
)


def parse_tbl_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """Trust Bank's Drupal card listing. No date on the listing page."""
    notices = []
    for match in _TBL_CARD.finditer(html):
        title_m = _TBL_TITLE.search(match.group(1))
        if not title_m:
            continue
        title = strip_tags(title_m.group(2))
        if looks_like_junk_title(title):
            continue
        notices.append(
            ParsedNotice(title, "", absolute_url(title_m.group(1), source_url))
        )
    return notices


_IDLC_CARD = re.compile(r'<div[^>]*class="pdfDownloadItem"[^>]*>(.*?)</div>', re.I | re.S)
_FIRST_P = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_FIRST_HREF = re.compile(r'<a[^>]*href="([^"]+)"', re.I)


def parse_idlc_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    notices = []
    for match in _IDLC_CARD.finditer(html):
        card = match.group(1)
        title_m = _FIRST_P.search(card)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue
        link_m = _FIRST_HREF.search(card)
        link = absolute_url(link_m.group(1), source_url) if link_m else ""
        notices.append(ParsedNotice(title, "", link))
    return notices


_ICDDRB_CARD = re.compile(r'<div[^>]*class="row mx-1"[^>]*>(.*?)</div>\s*</div>', re.I | re.S)
_ICDDRB_TITLE = re.compile(r'<a[^>]*class="header"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_ICDDRB_DATE = re.compile(r"Published:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", re.I)


def parse_icddrb_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    notices = []
    for match in _ICDDRB_CARD.finditer(html):
        card = match.group(1)
        title_m = _ICDDRB_TITLE.search(card)
        if not title_m:
            continue
        title = strip_tags(title_m.group(2))
        if looks_like_junk_title(title):
            continue
        date_m = _ICDDRB_DATE.search(card)
        notices.append(
            ParsedNotice(
                title,
                date_m.group(1) if date_m else "",
                absolute_url(title_m.group(1), source_url),
            )
        )
    return notices


_SB_CARD = re.compile(
    r'<a[^>]*class="form-d-card-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
)


def parse_standardbank_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    notices = []
    for match in _SB_CARD.finditer(html):
        title_m = _FIRST_P.search(match.group(2))
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue
        notices.append(
            ParsedNotice(title, "", absolute_url(match.group(1), source_url))
        )
    return notices


_DBBL_CARD = re.compile(r'<div class="well">(.*?)</div>', re.I | re.S)
_DBBL_TITLE = re.compile(r"<h4>(.*?)</h4>", re.I | re.S)


def parse_dbbl_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    """DBBL mixes .jpg and .pdf attachments; only real PDFs are kept."""
    notices = []
    for match in _DBBL_CARD.finditer(html):
        card = match.group(1)
        title_m = _DBBL_TITLE.search(card)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue
        pdf = find_pdf_link(card)
        if not pdf:
            continue
        notices.append(ParsedNotice(title, "", absolute_url(pdf, source_url)))
    return notices


_IFIC_PANEL = re.compile(
    r'<div class="panel">(.*?)</div>\s*</div>\s*</div>\s*</div>', re.I | re.S
)
_IFIC_TITLE = re.compile(r'<a[^>]*class="accordion-toggle[^"]*"[^>]*>(.*?)</a>', re.I | re.S)
_IFIC_LINK = re.compile(r'<a[^>]*href="([^"]+)"[^>]*download', re.I)


def parse_ific_panels(html: str, source_url: str, **_) -> list[ParsedNotice]:
    notices = []
    for match in _IFIC_PANEL.finditer(html):
        panel = match.group(1)
        title_m = _IFIC_TITLE.search(panel)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue
        link_m = _IFIC_LINK.search(panel)
        link = absolute_url(link_m.group(1), source_url) if link_m else ""
        notices.append(ParsedNotice(title, "", link))
    return notices


_METLIFE_CARD = re.compile(
    r'<div class="col-12 col-sm-6 col-md-4 article-list-item">(.*?)</div>\s*</div>\s*</div>',
    re.I | re.S,
)
_METLIFE_DATE = re.compile(
    r'<span[^>]*class="article-list-item-publishedDate[^"]*"[^>]*>(.*?)</span>', re.I | re.S
)
_METLIFE_LINK = re.compile(r'<a[^>]*href="([^"]+)"[^>]*target="_self"', re.I)
_METLIFE_TITLE = re.compile(r'<div class="article-list-item-headline">(.*?)</div>', re.I | re.S)


def parse_metlife_cards(html: str, source_url: str, **_) -> list[ParsedNotice]:
    notices = []
    for match in _METLIFE_CARD.finditer(html):
        card = match.group(1)
        title_m = _METLIFE_TITLE.search(card)
        title = strip_tags(title_m.group(1)) if title_m else ""
        if looks_like_junk_title(title):
            continue
        date_m = _METLIFE_DATE.search(card)
        link_m = _METLIFE_LINK.search(card)
        notices.append(
            ParsedNotice(
                title,
                strip_tags(date_m.group(1)) if date_m else "",
                absolute_url(link_m.group(1), source_url) if link_m else "",
            )
        )
    return notices


STRATEGIES = {
    "data-column": parse_data_column,
    "positional": parse_positional,
    "citybank-list": parse_citybank_list,
    "mtb-list": parse_mtb_list,
    "heat-cards": parse_heat_cards,
    "gp-cards": parse_gp_cards,
    "tbl-cards": parse_tbl_cards,
    "idlc-cards": parse_idlc_cards,
    "icddrb-cards": parse_icddrb_cards,
    "standardbank-cards": parse_standardbank_cards,
    "dbbl-cards": parse_dbbl_cards,
    "ific-panels": parse_ific_panels,
    "metlife-cards": parse_metlife_cards,
}


class UnknownStrategy(Exception):
    """The site has no parsing strategy configured."""


def parse_page(
    html: str, *, site_name: str, source_url: str, strategy: str | None = None
) -> list[ParsedNotice]:
    """Extract notices from one page of a site's listing.

    `strategy` overrides the built-in mapping, so an admin can change a site's
    strategy through the API without a code change.
    """
    if not html or len(html) < MIN_USABLE_HTML:
        return []

    strategy = strategy or SITE_STRATEGIES.get(site_name)
    if not strategy:
        raise UnknownStrategy(
            f"No parsing strategy configured for {site_name!r}. "
            f"Set one on the site, or add it to SITE_STRATEGIES."
        )

    parser = STRATEGIES.get(strategy)
    if parser is None:
        raise UnknownStrategy(
            f"Unknown strategy {strategy!r} for {site_name!r}. "
            f"Known strategies: {', '.join(sorted(STRATEGIES))}."
        )

    return parser(
        html, source_url, columns=POSITIONAL_COLUMNS.get(site_name)
    )

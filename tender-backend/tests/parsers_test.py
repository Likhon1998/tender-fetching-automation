"""Tests for the per-site HTML parsers.

Each strategy has a fixture in tests/fixtures/ modelled on the real markup of
the site it came from. The expected values below were verified against the
original n8n JavaScript parser running on the same fixtures: all 13 strategies
produced byte-identical output, so these expectations encode the production
behaviour rather than my reading of it.

Run with:  PYTHONPATH=. python tests/parsers_test.py
"""

from pathlib import Path

from app.ingestion.parsers import (
    POSITIONAL_COLUMNS,
    SITE_STRATEGIES,
    STRATEGIES,
    UnknownStrategy,
    parse_page,
)

FIXTURES = Path(__file__).parent / "fixtures"

failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(label)
        print(f"  FAIL {label}\n       expected: {expected!r}\n       got:      {got!r}")
    else:
        print(f"  ok   {label}")


def parse(strategy, site, url):
    html = (FIXTURES / f"{strategy}.html").read_text(encoding="utf-8")
    return parse_page(html, site_name=site, source_url=url)


# (strategy, site, source url, expected notices)
CASES = [
    (
        "data-column", "DPE", "https://dpe.gov.bd/pages/tenders",
        [
            ("Procurement of Firewall Appliances for Head Office", "2026-06-15",
             "https://dpe.gov.bd/files/notice1.pdf"),
            ("Supply of Laptop Computers", "2026-07-01",
             "https://dpe.gov.bd/files/notice2.pdf"),
        ],
    ),
    (
        "positional", "MeghnaBank", "https://www.meghnabank.com.bd/notice-board",
        [
            ("Tender for Network Switches and Routers", "15-Jun-2026",
             "https://www.meghnabank.com.bd/docs/a.pdf"),
            ("RFP for Data Center Migration Services", "01/07/2026",
             "https://x.test/b.pdf"),
        ],
    ),
    (
        "citybank-list", "CityBank", "https://www.citybankplc.com/rfp/request-for-proposal",
        [
            ("RFP for CMMI-DEV Level 3 Consultancy. Date of submission: on or before August 30, 2026 at 04:00PM",
             "August 30, 2026", ""),
            ("RFQ for Renewal of Proxy System Support before September 15, 2026",
             "September 15, 2026", ""),
        ],
    ),
    (
        "mtb-list", "MTB", "https://www.mutualtrustbank.com/news-events/",
        [("Tender Notice for IT Equipment Supply", None,
          "https://www.mutualtrustbank.com/news/1")],
    ),
    (
        "heat-cards", "HEAT_UGC", "https://heat.ugc.gov.bd/tenders-and-circulars",
        [
            ("Procurement of Server Hardware for Universities", "Jun 23, 2026",
             "https://heat.ugc.gov.bd/files/heat1.pdf"),
            ("Consultancy for Digital Library System", "Jul 02, 2026",
             "https://heat.ugc.gov.bd/files/heat2.pdf"),
        ],
    ),
    (
        "gp-cards", "Grameenphone", "https://www.grameenphone.com/bn/useful-links/notice-board",
        [("সফটওয়্যার উন্নয়ন সংক্রান্ত দরপত্র বিজ্ঞপ্তি", None,
          "https://www.grameenphone.com/notice/1")],
    ),
    (
        "tbl-cards", "TBL", "https://www.tblbd.com/tender",
        [("Supply of Network Security Appliance", "", "https://www.tblbd.com/tender/1")],
    ),
    (
        "idlc-cards", "IDLC", "https://idlc.com/e-tender",
        [
            ("Tender for Core Banking Software Upgrade", "", "https://idlc.com/pdf/1.pdf"),
            ("RFQ for Cyber Security Audit", "", "https://idlc.com/pdf/2.pdf"),
        ],
    ),
    (
        "icddrb-cards", "ICDDRB", "https://www.icddrb.org/tender-notices",
        [("Procurement of Laboratory Information System", "12 June 2026",
          "https://www.icddrb.org/tender/55")],
    ),
    (
        "standardbank-cards", "StandardBank", "https://www.standardbankbd.com/FeaturedNews.php",
        [
            ("Tender Notice for ATM Network Expansion", "",
             "https://www.standardbankbd.com/files/sb1.pdf"),
            ("RFP for Managed IT Services", "",
             "https://www.standardbankbd.com/files/sb2.pdf"),
        ],
    ),
    (
        "dbbl-cards", "DBBL", "https://www.dutchbanglabank.com/tender/tender.html",
        [("Tender for Data Center UPS Replacement", "",
          "https://www.dutchbanglabank.com/doc/a.pdf")],
    ),
    (
        "ific-panels", "IFIC", "https://ificbank.com.bd/notice",
        [("Procurement of Firewall and IPS Solution", "",
          "https://ificbank.com.bd/files/ific1.pdf")],
    ),
    (
        "metlife-cards", "MetLife", "https://www.metlife.com.bd/about-us/newsroom/",
        [("Request for Proposal: CRM System Implementation", "15 July 2026",
          "https://www.metlife.com.bd/news/1")],
    ),
]

print("=== per-site parsers ===")
for strategy, site, url, expected in CASES:
    notices = parse(strategy, site, url)
    check(f"{strategy}: notice count", len(notices), len(expected))
    for got, (title, date_raw, link) in zip(notices, expected):
        check(f"{strategy}: title", got.title, title)
        # date_raw None means "whatever the current year makes it" — these
        # sites publish a month and day but no year.
        if date_raw is not None:
            check(f"{strategy}: date", got.date_raw, date_raw)
        check(f"{strategy}: link", got.pdf_link, link)

print("\n=== a second date column is read as the deadline ===")
notices = parse("positional-two-dates", "BangladeshBank",
                "https://www.bb.org.bd/en/index.php/about/tenders")
check("both rows parsed", len(notices), 2)
check("publish date", notices[0].date_raw, "24-08-2026")
check("submission date", notices[0].submission_raw, "14-09-2026")
check("sites without a deadline column give none",
      parse("positional", "MeghnaBank",
            "https://www.meghnabank.com.bd/notice-board")[0].submission_raw, "")

print("\n=== a deadline column is found without per-site configuration ===")
# Only Bangladesh Bank has its deadline column configured explicitly. Every
# other positional site relies on detection: a later date in the same row.
notices = parse("positional-three-dates", "BangladeshBank",
                "https://www.bb.org.bd/en/index.php/about/tenders")
check("publish date read", notices[0].date_raw, "24-08-2026")
check("later date taken as the deadline", notices[0].submission_raw, "20-09-2026")

notices = parse("positional-one-date", "MeghnaBank",
                "https://www.meghnabank.com.bd/notice-board")
check("one date column invents nothing", notices[0].submission_raw, "")
check("and still reads the publish date", notices[0].date_raw, "15-Jun-2026")

print("\n=== junk rows are skipped ===")
notices = parse("positional", "MeghnaBank", "https://www.meghnabank.com.bd/notice-board")
titles = [n.title for n in notices]
check("row whose title is a date is dropped", any("05-08-2026" in t for t in titles), False)

notices = parse("data-column", "DPE", "https://dpe.gov.bd/pages/tenders")
check("hidden portal row is dropped",
      any("Hidden row" in n.title for n in notices), False)
check("numeric-only title is dropped", any(n.title == "12" for n in notices), False)

print("\n=== attachments ===")
notices = parse("dbbl-cards", "DBBL", "https://www.dutchbanglabank.com/tender/tender.html")
check("image-only notice is dropped",
      any("image attachment" in n.title for n in notices), False)

print("\n=== guards ===")
check("empty html yields nothing", parse_page("", site_name="DPE", source_url="x"), [])
check("truncated html yields nothing",
      parse_page("<html></html>", site_name="DPE", source_url="x"), [])

try:
    parse_page("x" * 300, site_name="NotARealSite", source_url="x")
    check("unknown site raises", False, True)
except UnknownStrategy:
    check("unknown site raises", True, True)

try:
    parse_page("x" * 300, site_name="DPE", source_url="x", strategy="nonsense")
    check("unknown strategy raises", False, True)
except UnknownStrategy:
    check("unknown strategy raises", True, True)

print("\n=== configuration is complete ===")
check("every strategy name has a parser",
      sorted(set(SITE_STRATEGIES.values())), sorted(STRATEGIES))
check("every positional site has columns",
      sorted(s for s, v in SITE_STRATEGIES.items() if v == "positional"),
      sorted(POSITIONAL_COLUMNS))
check("all 38 sites are configured", len(SITE_STRATEGIES), 38)

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    raise SystemExit(1)
print("ALL PARSER CHECKS PASSED")

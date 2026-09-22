"""Tests for the keyword classifier and date parsing.

These need no database or network: the classifier is pure logic, which is why
it is worth testing in isolation before wiring it to scraping.

Run with:  PYTHONPATH=. python tests/classifier_test.py
"""

from datetime import date
from decimal import Decimal

from app.data.reference_data import CATEGORIES
from app.ingestion.classifier import Classifier
from app.ingestion.dates import bengali_digits_to_ascii, is_within_cutoff, normalise_date

clf = Classifier([(i + 1, c["name"], c["keywords"]) for i, c in enumerate(CATEGORIES)])
failures = []


def check(label, got, expected):
    if got != expected:
        failures.append(f"{label}: expected {expected!r}, got {got!r}")
        print(f"  FAIL {label}: expected {expected!r}, got {got!r}")
    else:
        print(f"  ok   {label}")


def category_of(title):
    r = clf.classify(title)
    return r.category_name if r else None


print("=== date parsing ===")
for raw, expected in [
    ("2026-08-30", date(2026, 8, 30)),
    ("30-Aug-2026", date(2026, 8, 30)),
    ("Aug 30, 2026", date(2026, 8, 30)),
    ("30/08/2026", date(2026, 8, 30)),
    ("08.30.2026", date(2026, 8, 30)),
    ("15/02/2026", date(2026, 2, 15)),
    ("০৪-Dec-২০২৬", date(2026, 12, 4)),
    ("2026", None),
    ("", None),
    ("sometime soon", None),
    ("31-Feb-2026", None),
]:
    check(f"parse {raw!r}", normalise_date(raw)[0], expected)

check("raw text always kept", normalise_date("  weird text  ")[1], "weird text")
check("bengali digits", bengali_digits_to_ascii("২০২৬"), "2026")

print("\n=== cutoff year ===")
for raw, expected in [
    ("2025-12-31", False), ("2026-01-01", True), ("04-12-2025", False),
    ("Dec 4, 2026", True), ("", True), ("2025", True), ("unparseable", True),
]:
    check(f"keep {raw!r}", is_within_cutoff(raw, 2026), expected)

print("\n=== classification ===")
for title, expected in [
    ("Procurement of Firewall and Network Security Appliances", "Network Security"),
    ("Tender for Cyber Security Audit and VAPT Services", "Cyber Security"),
    ("Procurement of Cloud Hosting and Backup Services", "Cloud Services"),
    ("Request for Proposal: Data Center Migration and DR Setup", "Data Center Solutions"),
    ("Procurement of Laptop Computers for Field Offices", "IT Infrastructures"),
    ("System Integration Services for Payment Gateway", "System Integration"),
    ("সফটওয়্যার উন্নয়ন সংক্রান্ত দরপত্র বিজ্ঞপ্তি", "Software Development"),
    ("কম্পিউটার ও প্রিন্টার সরবরাহের দরপত্র", "IT Infrastructures"),
]:
    check(f"{title[:42]!r}", category_of(title), expected)

print("\n=== irrelevant notices are rejected ===")
for title in [
    "Notice for Disposal of Old Office Furniture",
    "Auction Notice for Vehicle Sale",
    "Recruitment Notice for Office Assistant",
    "Construction of boundary wall at head office",
    "Tender notice",
    "",
]:
    check(f"reject {title[:38]!r}", category_of(title), None)

print("\n=== short abbreviations need word boundaries ===")
for title in [
    "Interpretation services for the conference",   # contains "erp"
    "Maintenance of office air conditioning",       # contains "ai"
    "This notice is hereby published",              # contains "his"
]:
    check(f"no false hit {title[:36]!r}", category_of(title), None)

print("\n=== weak evidence is discarded ===")
r = clf.classify("Supply of stationery and paper")
check("single short keyword rejected", r, None)

print("\n=== confidence ===")
r = clf.classify("Procurement of Threat Intelligence solution for Threat Hunting")
check("strong match caps at 1", r.confidence, Decimal("1.000"))
check("confidence has 3 decimal places",
      clf.classify("Consultancy Services for Digital Transformation").confidence.as_tuple().exponent, -3)
check("keyword count", clf.keyword_count, sum(len(c["keywords"]) for c in CATEGORIES))

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    raise SystemExit(1)
print("ALL CLASSIFIER CHECKS PASSED")
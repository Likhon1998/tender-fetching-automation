"""Insert sample tenders so the browse screen can be built and tested before
the scraper exists.

Run with:   python -m scripts.seed_sample_tenders
Remove with: python -m scripts.seed_sample_tenders --clear

Every row is tagged [SAMPLE] in the title so it is obvious in the database and
so --clear can remove them without touching real data.
"""

import asyncio
import random
import sys
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.site import Site
from app.models.tender import STATUS_NEW, STATUS_NOT_INTERESTED, Tender

MARKER = "[SAMPLE]"

TITLES = [
    ("Procurement of Firewall and Network Security Appliances", "Network Security"),
    ("Supply and Installation of Core Banking Software", "Enterprise Resource Planning (ERP)"),
    ("Tender for Cyber Security Audit and VAPT Services", "Cyber Security"),
    ("Procurement of Laptop Computers for Field Offices", "IT Infrastructures"),
    ("Development of Hospital Management Information System", "Healthcare Solution"),
    ("Request for Proposal: Data Center Migration and DR Setup", "Data Center Solutions"),
    ("Annual Maintenance Contract for IT Equipment", "Managed Services"),
    ("Procurement of Cloud Hosting and Backup Services", "Cloud Services"),
    ("Consultancy Services for Digital Transformation Roadmap", "Training & Consultancy"),
    ("Supply of Manpower for Software Testing", "Resource Augmentation"),
    ("Development of Mobile Banking Application", "Software Development"),
    ("Procurement of Business Intelligence and Reporting Platform", "Business Intelligence (BI) & Artificial Intelligence (AI)"),
    ("Implementation of Document Management System", "Workflow & Collaboration Tools"),
    ("Supply of Identity and Access Management Solution", "Secure Access & Collaboration"),
    ("System Integration Services for Payment Gateway", "System Integration"),
    ("সফটওয়্যার উন্নয়ন সংক্রান্ত দরপত্র বিজ্ঞপ্তি", "Software Development"),
    ("কম্পিউটার ও প্রিন্টার সরবরাহের দরপত্র", "IT Infrastructures"),
    ("Notice for Disposal of Old Office Furniture", None),
    ("Auction Notice for Vehicle Sale", None),
    ("Tender for Canteen Management Services", None),
]


async def clear() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Tender).where(Tender.title.like(f"%{MARKER}%"))
        )
        await db.commit()
        return result.rowcount or 0


async def seed() -> int:
    rng = random.Random(42)  # fixed seed so repeated runs are reproducible

    async with AsyncSessionLocal() as db:
        sites = list((await db.execute(select(Site))).scalars().all())
        categories = {
            c.name: c for c in (await db.execute(select(Category))).scalars().all()
        }
        if not sites:
            print("No sites found. Run seed_reference_data first.")
            return 0

        existing = set(
            (await db.execute(select(Tender.title))).scalars().all()
        )

        created = 0
        today = date.today()

        for index, (title, category_name) in enumerate(TITLES):
            site = sites[index % len(sites)]
            full_title = f"{title} {MARKER} {site.name}"
            if full_title in existing:
                continue

            category = categories.get(category_name) if category_name else None

            # A spread of dates, plus a couple with none at all, since several
            # of the real sites publish notices without a date.
            if index % 7 == 0:
                published, raw = None, ""
            else:
                published = today - timedelta(days=rng.randint(0, 240))
                raw = published.strftime("%d-%b-%Y")

            db.add(
                Tender(
                    title=full_title,
                    date=published,
                    date_raw=raw,
                    pdf_link=f"{site.url.rstrip('/')}/notice-{index + 1}.pdf",
                    site_id=site.id,
                    source_name=site.name,
                    source_url=site.url,
                    category_id=category.id if category else None,
                    category=category.name if category else None,
                    confidence=round(rng.uniform(0.45, 1.0), 3) if category else None,
                    status=STATUS_NOT_INTERESTED if index % 9 == 0 else STATUS_NEW,
                )
            )
            created += 1

        await db.commit()
        return created


async def main() -> int:
    if "--clear" in sys.argv:
        removed = await clear()
        print(f"Removed {removed} sample tender(s).")
        return 0

    created = await seed()
    print(f"Created {created} sample tender(s).")
    if created:
        print(f"Remove them later with: python -m scripts.seed_sample_tenders --clear")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
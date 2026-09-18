"""
Development database seed script.

Run with:  python -m app.db.seed

Seeds the database with the SAME prototype/demo data already used by the
frontend's mock layer (src/data/mockStandards.ts, mockSchemes.ts,
mockLabs.ts) — ported here by hand, value for value, not invented. Every
row is written with source_type="demo" to make clear this is NOT verified
official BIS information (per this phase's explicit requirement to never
silently present mock data as official).

Idempotent: running this command multiple times does not create duplicate
rows. Standards are matched by their unique `code`; schemes by `name`;
labs by `name` — if a row with that key already exists, it is left alone
rather than duplicated or overwritten.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.certification_scheme import CertificationScheme, CertificationStep, SchemeEligibility
from app.models.lab import Lab, LabAccreditation, LabTestCategory
from app.models.standard import Standard, StandardRelatedCode

# --- Source data, ported value-for-value from src/data/mockStandards.ts ---
DEMO_STANDARDS = [
    dict(
        code="IS 302-1",
        title="Safety of Household and Similar Electrical Appliances, Part 1: General Requirements",
        category="Electrical Appliances",
        description=(
            "Specifies general safety requirements for household and similar electrical appliances, "
            "covering protection against electric shock, mechanical hazards, and fire."
        ),
        status="active",
        last_amended=date(2023, 4, 11),
        sector="Electronics & Electrical",
        related_codes=["IS 302-2", "IEC 60335-1"],
    ),
    dict(
        code="IS 1786",
        title="High Strength Deformed Steel Bars and Wires for Concrete Reinforcement",
        category="Construction Materials",
        description=(
            "Covers requirements for high strength deformed steel bars and wires used for reinforcement "
            "of concrete structures, including chemical composition and tensile properties."
        ),
        status="active",
        last_amended=date(2022, 8, 2),
        sector="Construction & Infrastructure",
        related_codes=["IS 432", "IS 1139"],
    ),
    dict(
        code="IS 15885",
        title="Hallmarking of Gold Jewellery and Artefacts",
        category="Precious Metals",
        description=(
            "Specifies requirements for hallmarking of gold jewellery and artefacts, including fineness "
            "grades, marking symbols, and testing methods."
        ),
        status="active",
        last_amended=date(2021, 11, 19),
        sector="Jewellery & Precious Metals",
        related_codes=["IS 1417", "IS 2790"],
    ),
    dict(
        code="IS 16046",
        title="Face Masks for General Use — Specification",
        category="Personal Protective Equipment",
        description=(
            "Specifies requirements, sampling and test methods for reusable and single-use face masks "
            "intended for general public use."
        ),
        status="active",
        last_amended=date(2020, 6, 15),
        sector="Healthcare & Safety",
        related_codes=["IS 9873"],
    ),
    dict(
        code="IS 4905",
        title="Random Sampling and Randomization Methods",
        category="Quality Management",
        description=(
            "Provides methods for random sampling and randomization to be applied during quality "
            "inspection and conformity assessment procedures."
        ),
        status="under-revision",
        last_amended=date(2019, 1, 10),
        sector="Quality Management",
        related_codes=["IS/ISO 2859-1"],
    ),
    dict(
        code="IS 14625",
        title="Packaged Drinking Water (Other than Natural Mineral Water) — Specification",
        category="Food & Beverages",
        description=(
            "Specifies quality, safety, and labelling requirements for packaged drinking water sold for "
            "human consumption."
        ),
        status="active",
        last_amended=date(2023, 2, 28),
        sector="Food & Public Distribution",
        related_codes=["IS 13428"],
    ),
    dict(
        code="IS 13360",
        title="Plastics — Methods of Testing, Part 1: General Guidelines",
        category="Plastics & Polymers",
        description=(
            "Lays down general guidelines and terminology for methods used to test plastic materials and "
            "products across all parts of this standard series."
        ),
        status="active",
        last_amended=date(2020, 9, 5),
        sector="Manufacturing",
        related_codes=["IS 13360-3"],
    ),
    dict(
        code="IS 2062",
        title="Hot Rolled Medium and High Tensile Structural Steel — Specification",
        category="Metals & Alloys",
        description=(
            "Covers requirements for hot rolled steel plates, strips, shapes and sections used in "
            "structural applications including welded, bolted, and riveted construction."
        ),
        status="active",
        last_amended=date(2022, 5, 30),
        sector="Construction & Infrastructure",
        related_codes=["IS 800"],
    ),
]

# --- Source data, ported value-for-value from src/data/mockSchemes.ts ---
DEMO_SCHEMES = [
    dict(
        name="Product Certification Scheme (ISI Mark)",
        type="product-certification",
        summary=(
            "Voluntary and mandatory certification allowing manufacturers to use the ISI Mark, certifying "
            "that products conform to relevant Indian Standards."
        ),
        eligibility=[
            "Manufacturing unit with in-house or accredited testing facility",
            "Product covered under an existing Indian Standard",
            "Compliance with quality control requirements specified in the scheme",
        ],
        steps=[
            ("Application Submission", "Submit application with product and factory details via the BIS portal."),
            ("Factory Evaluation", "BIS officers conduct an on-site audit of manufacturing and testing facilities."),
            ("Sample Testing", "Product samples are tested against the applicable Indian Standard."),
            ("Grant of License", "On satisfactory evaluation, BIS grants the license to use the Standard Mark."),
        ],
        average_duration_days=90,
        fees="₹1,000 application fee + testing and marking fees as per scheme",
    ),
    dict(
        name="Hallmarking Scheme for Gold Jewellery",
        type="hallmarking",
        summary=(
            "Certification scheme ensuring gold jewellery and artefacts meet declared purity standards "
            "through registered Assaying & Hallmarking Centres."
        ),
        eligibility=[
            "Jewellers registered under the BIS Hallmarking Scheme",
            "Products conforming to permitted fineness grades (e.g. 22K916, 18K750, 14K585)",
        ],
        steps=[
            ("Jeweller Registration", "Register as a BIS-recognized jeweller via the online portal."),
            ("Submit to AHC", "Submit jewellery items to a registered Assaying & Hallmarking Centre."),
            ("Purity Testing", "AHC tests fineness/purity using approved methods."),
            ("Hallmark Application", "Approved items receive the BIS hallmark with unique HUID."),
        ],
        average_duration_days=3,
        fees="Nominal per-piece hallmarking charge as notified by BIS",
    ),
    dict(
        name="Compulsory Registration Scheme (CRS)",
        type="product-certification",
        summary=(
            "Applicable to electronics and IT products notified under the Electronics and IT Goods "
            "(Requirements for Compulsory Registration) Order, ensuring safety compliance before sale in India."
        ),
        eligibility=[
            "Product listed under the notified CRS product list",
            "Testing conducted at a BIS-recognized laboratory",
        ],
        steps=[
            ("Lab Testing", "Get the product tested at a BIS-recognized lab against the applicable safety standard."),
            ("Online Registration", "Submit test reports and product details on the CRS portal."),
            ("Registration Grant", "BIS reviews and grants registration allowing legal sale of the product."),
        ],
        average_duration_days=30,
        fees="Registration fee per model as per CRS fee schedule",
    ),
    dict(
        name="Management System Certification",
        type="management-system",
        summary=(
            "Certification of Quality (ISO 9001), Environmental (ISO 14001), and other management systems "
            "for organizations seeking process-level conformity recognition."
        ),
        eligibility=[
            "Documented management system in operation for a minimum period",
            "Internal audits and management review completed",
        ],
        steps=[
            (
                "Application & Documentation Review",
                "Submit application along with the management system manual and records.",
            ),
            ("Stage 1 Audit", "BIS assessors review documentation and readiness for certification audit."),
            ("Stage 2 Audit", "On-site audit verifying implementation and effectiveness of the management system."),
            ("Certification Decision", "Certificate issued upon successful closure of non-conformities, if any."),
        ],
        average_duration_days=60,
        fees="As per man-day audit charges based on organization size",
    ),
]

# --- Source data, ported value-for-value from src/data/mockLabs.ts ---
DEMO_LABS = [
    dict(
        name="National Test House (Eastern Region)",
        city="Kolkata",
        state="West Bengal",
        accreditations=["NABL", "BIS-Recognized"],
        test_categories=["Electrical Appliances", "Textiles", "Chemicals"],
        contact="nth-er@example.gov.in",
    ),
    dict(
        name="Shriram Institute for Industrial Research",
        city="New Delhi",
        state="Delhi",
        accreditations=["NABL", "ISO-17025"],
        test_categories=["Food & Beverages", "Plastics & Polymers", "Cosmetics"],
        contact="contact@shriraminstitute.example.org",
    ),
    dict(
        name="Central Institute of Plastics Engineering & Technology (CIPET)",
        city="Chennai",
        state="Tamil Nadu",
        accreditations=["BIS-Recognized", "ISO-17025"],
        test_categories=["Plastics & Polymers", "Packaging"],
        contact="testing@cipet.example.gov.in",
    ),
    dict(
        name="Electronics Regional Test Laboratory",
        city="Bengaluru",
        state="Karnataka",
        accreditations=["NABL", "BIS-Recognized"],
        test_categories=["Electronics & Electrical", "IT Equipment"],
        contact="ertl-blr@example.gov.in",
    ),
    dict(
        name="Regional Assaying & Hallmarking Centre",
        city="Jaipur",
        state="Rajasthan",
        accreditations=["BIS-Recognized"],
        test_categories=["Precious Metals"],
        contact="rahc-jaipur@example.gov.in",
    ),
    dict(
        name="National Metallurgical Laboratory",
        city="Jamshedpur",
        state="Jharkhand",
        accreditations=["NABL", "ISO-17025"],
        test_categories=["Metals & Alloys", "Construction Materials"],
        contact="nml-testing@example.gov.in",
    ),
]


def seed_standards(db: Session) -> int:
    created = 0
    for entry in DEMO_STANDARDS:
        existing = db.query(Standard).filter(Standard.code == entry["code"]).one_or_none()
        if existing:
            continue
        standard = Standard(
            id=str(uuid.uuid4()),
            code=entry["code"],
            title=entry["title"],
            category=entry["category"],
            description=entry["description"],
            status=entry["status"],
            last_amended=entry["last_amended"],
            sector=entry["sector"],
            source_type="demo",
        )
        standard.related_codes = [StandardRelatedCode(code=c) for c in entry["related_codes"]]
        db.add(standard)
        created += 1
    db.commit()
    return created


def seed_schemes(db: Session) -> int:
    created = 0
    for entry in DEMO_SCHEMES:
        existing = db.query(CertificationScheme).filter(CertificationScheme.name == entry["name"]).one_or_none()
        if existing:
            continue
        scheme = CertificationScheme(
            id=str(uuid.uuid4()),
            name=entry["name"],
            type=entry["type"],
            summary=entry["summary"],
            average_duration_days=entry["average_duration_days"],
            fees=entry["fees"],
            source_type="demo",
        )
        scheme.eligibility_items = [
            SchemeEligibility(order=i, requirement=req) for i, req in enumerate(entry["eligibility"], start=1)
        ]
        scheme.steps = [
            CertificationStep(order=i, title=title, description=desc)
            for i, (title, desc) in enumerate(entry["steps"], start=1)
        ]
        db.add(scheme)
        created += 1
    db.commit()
    return created


def seed_labs(db: Session) -> int:
    created = 0
    for entry in DEMO_LABS:
        existing = db.query(Lab).filter(Lab.name == entry["name"]).one_or_none()
        if existing:
            continue
        lab = Lab(
            id=str(uuid.uuid4()),
            name=entry["name"],
            city=entry["city"],
            state=entry["state"],
            contact=entry["contact"],
            source_type="demo",
        )
        lab.accreditations = [LabAccreditation(accreditation=a) for a in entry["accreditations"]]
        lab.test_categories = [LabTestCategory(category=c) for c in entry["test_categories"]]
        db.add(lab)
        created += 1
    db.commit()
    return created


def run_seed() -> None:
    db = SessionLocal()
    try:
        standards_created = seed_standards(db)
        schemes_created = seed_schemes(db)
        labs_created = seed_labs(db)
        print(
            f"Seed complete. Created: {standards_created} standards, "
            f"{schemes_created} certification schemes, {labs_created} labs. "
            f"(Existing matching rows were left untouched — safe to re-run.)"
        )
        print("All seeded rows are marked source_type='demo' — this is prototype data, not verified official BIS information.")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()

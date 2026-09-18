"""
Clarification-question framework — Phase 10.

Given a ProductProfile, decides which questions still need to be asked
before the profile has enough information for reliable standard
identification. Deliberately a small, reusable, table-driven framework
rather than one hardcoded product category: adding a new category means
adding an entry to CATEGORY_QUESTIONS, not touching any control-flow code
here.

A small, seeded set of categories is included (water heater, water
purifier) plus a generic fallback for any other/unrecognized category —
enough to demonstrate the framework works across more than one product
type, without pretending to model the full space of BIS-regulated
products.
"""

from dataclasses import dataclass

from app.models.product_profile import ProductProfile


@dataclass
class ClarificationQuestion:
    field: str  # the ProductProfile field this question is meant to fill
    question: str


# Each category maps to an ordered list of (field, question) pairs asked
# only when that field is still None on the profile. `product_category`
# itself is asked first, universally, via GENERIC_QUESTIONS below — a
# category can only be selected once the user has said enough to imply one
# (see classify_category in profile_extraction.py).
CATEGORY_QUESTIONS: dict[str, list[ClarificationQuestion]] = {
    "water_heater": [
        ClarificationQuestion("product_type", "Is it a storage-type or instant water heater?"),
        ClarificationQuestion("electrical_characteristics", "What is the rated voltage and power (e.g. 230V, 2000W)?"),
        ClarificationQuestion("capacity", "What is the water storage capacity (in litres), if applicable?"),
        ClarificationQuestion("intended_use", "Is this for domestic or commercial use?"),
        ClarificationQuestion("technology", "What heating technology is used (e.g. immersion element, heat pump)?"),
        ClarificationQuestion("materials", "What materials are in contact with the water (e.g. copper, stainless steel)?"),
    ],
    "water_purifier": [
        ClarificationQuestion("technology", "What purification technology does it use (RO, UV, UF, or another)?"),
        ClarificationQuestion("intended_use", "Is this for domestic or commercial use?"),
        ClarificationQuestion("electrical_characteristics", "What is its rated electrical input?"),
        ClarificationQuestion("capacity", "What is its water treatment capacity (e.g. litres/hour)?"),
    ],
}

# Asked before a category-specific list can even be selected — universal
# across every product.
GENERIC_QUESTIONS: list[ClarificationQuestion] = [
    ClarificationQuestion("product_category", "What kind of product is this (e.g. water heater, water purifier)?"),
]

# Asked once a category is known but doesn't match any seeded entry above —
# still useful, still never fabricates category-specific technical detail.
FALLBACK_QUESTIONS: list[ClarificationQuestion] = [
    ClarificationQuestion("product_type", "Can you describe the specific type or variant of this product?"),
    ClarificationQuestion("intended_use", "Is this for domestic, commercial, or industrial use?"),
    ClarificationQuestion("target_market", "Which market is this intended for (e.g. India)?"),
    ClarificationQuestion("manufacturing_location", "Where will this product be manufactured?"),
]


def missing_field_questions(profile: ProductProfile) -> list[ClarificationQuestion]:
    """Returns the next batch of clarification questions the profile still
    needs, in priority order. Never re-asks a field that already has a
    value — an already-answered attribute is never re-requested."""
    if not profile.product_category:
        return [q for q in GENERIC_QUESTIONS if getattr(profile, q.field) is None]

    question_set = CATEGORY_QUESTIONS.get(profile.product_category, FALLBACK_QUESTIONS)
    return [q for q in question_set if getattr(profile, q.field) is None]


def has_sufficient_information(profile: ProductProfile) -> bool:
    """A profile is 'sufficient' once no more clarification questions
    remain for its category. This does not mean every ProductProfile field
    is filled — only the fields that category's question set considers
    necessary."""
    return len(missing_field_questions(profile)) == 0

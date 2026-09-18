"""
Compliance checklist assembly — Phase 11.

Assembles a ComplianceChecklist from a ProductProfile, its evaluated
CandidateStandards, and extracted ComplianceRequirements. Contains no
extraction or applicability logic of its own — those stay in
requirement_extraction.py and applicability.py respectively, per the
existing separation-of-concerns pattern in app/product/. This module only
combines already-computed results into the one response object the
frontend renders.

A checklist is only assembled once has_sufficient_information(profile) is
true (see app/product/clarification.py) — the same gate Phase 10 already
uses to decide "enough is known to stop asking clarification questions."
Assembling a checklist before that point would mean generating
requirements from a profile too vague to have been evaluated for
applicability meaningfully.
"""

from app.models.product_profile import ProductProfile
from app.product.requirement_extraction import extract_requirements
from app.schemas.candidate_standard import CandidateStandard
from app.schemas.compliance import ComplianceChecklist
from app.schemas.product_profile import ProductProfileResponse


def _profile_to_response(profile: ProductProfile) -> ProductProfileResponse:
    return ProductProfileResponse(
        product_name=profile.product_name,
        product_category=profile.product_category,
        product_type=profile.product_type,
        intended_use=profile.intended_use,
        target_market=profile.target_market,
        manufacturing_location=profile.manufacturing_location,
        electrical_characteristics=profile.electrical_characteristics,
        capacity=profile.capacity,
        materials=profile.materials,
        technology=profile.technology,
        application=profile.application,
        other_attributes=profile.other_attributes,
    )


def build_checklist(
    profile: ProductProfile,
    candidates: list[CandidateStandard],
    open_questions: list[str],
    llm_provider=None,
) -> ComplianceChecklist:
    requirements = extract_requirements(candidates, llm_provider=llm_provider)
    return ComplianceChecklist(
        product_profile=_profile_to_response(profile),
        candidate_standards=candidates,
        items=requirements,
        open_questions=open_questions,
    )

"""
Applicability engine — Phase 10.

Decides each CandidateStandard's applicability_status. This is
deliberately rule-based, not LLM-based: semantic/keyword relevance alone
must never be upgraded to "this standard applies to your product" — that
requires the retrieved evidence to actually say something about the
product's stated category/type, or explicit regulatory metadata to exist
(none does yet — see module docstring below).

Current rule (intentionally simple, matching what real evidence in this
project can support today):
  - No product_category on the profile yet -> NEEDS_CLARIFICATION for
    every candidate: there's nothing yet to check the evidence against.
  - The candidate's evidence text does not literally mention the profile's
    product_category (or product_type) anywhere -> NEEDS_CLARIFICATION:
    it was retrieved (by similarity or keyword) but nothing in the actual
    evidence text confirms it's about this product.
  - The evidence textually mentions the category/type -> POTENTIALLY_APPLICABLE.
    Never escalated further to APPLICABLE by this engine: this project has
    no regulatory/QCO metadata anywhere (no StandardDocument/Standard field
    represents "mandatory," a conformity-assessment route, or a Quality
    Control Order) to justify a firmer determination. APPLICABLE is
    reserved for a future phase once that regulatory evidence exists.
  - NOT_APPLICABLE is not produced by this phase's rule at all — there is
    no positive evidence of exclusion to check for yet (e.g. an explicit
    "does not apply to X" statement). It remains a valid status value for
    a future rule to produce; a placeholder heuristic here would risk
    wrongly ruling out a genuinely relevant standard.

This module never touches an LLM. The LLM (Phase 10's "LLM role") only
explains an already-determined status in natural language — it does not
decide the status itself.
"""

from app.models.product_profile import ProductProfile
from app.schemas.candidate_standard import ApplicabilityStatus, CandidateStandard


def _evidence_mentions(candidate: CandidateStandard, terms: list[str]) -> bool:
    combined_text = " ".join(chunk.text for chunk in candidate.evidence).lower()
    return any(term.lower() in combined_text for term in terms if term)


def determine_applicability(candidate: CandidateStandard, profile: ProductProfile) -> CandidateStandard:
    """Returns a copy of `candidate` with applicability_status and
    applicability_reason set according to the rules above. Does not
    mutate the input in place, matching Pydantic model conventions
    elsewhere in this codebase (schemas are treated as values)."""
    if not profile.product_category:
        return candidate.model_copy(
            update={
                "applicability_status": ApplicabilityStatus.NEEDS_CLARIFICATION,
                "applicability_reason": "Product category is not yet known, so applicability cannot be assessed.",
            }
        )

    check_terms = [t for t in (profile.product_category, profile.product_type) if t]
    if _evidence_mentions(candidate, check_terms):
        return candidate.model_copy(
            update={
                "applicability_status": ApplicabilityStatus.POTENTIALLY_APPLICABLE,
                "applicability_reason": (
                    f"Retrieved evidence from {candidate.document_name} references the stated product "
                    f"category/type, but no regulatory (QCO/mandatory-certification) evidence is available "
                    f"in this system yet to confirm mandatory applicability."
                ),
            }
        )

    return candidate.model_copy(
        update={
            "applicability_status": ApplicabilityStatus.NEEDS_CLARIFICATION,
            "applicability_reason": (
                f"{candidate.document_name} was retrieved as potentially relevant, but its evidence text does "
                f"not explicitly reference the stated product category/type — more information or a document "
                f"review is needed."
            ),
        }
    )


def evaluate_candidates(candidates: list[CandidateStandard], profile: ProductProfile) -> list[CandidateStandard]:
    return [determine_applicability(candidate, profile) for candidate in candidates]

"""
Requirement extraction — Phase 11.

Turns a CandidateStandard's retrieved evidence into ComplianceRequirement
objects. Category and requirement-existence detection are 100%
deterministic keyword/pattern rules — never an LLM judgment call. This was
an explicit design decision (confirmed before implementation): the
evidence available in this project today is only synthetic test fixtures
with generic placeholder text, so an LLM-assisted extraction approach
would be both unverifiable against real BIS phrasing and would reintroduce
exactly the class of fabrication risk that app/product/response_safety.py
was built to catch in Phase 10 (the live-observed incident where
qwen2.5:7b invented IS numbers and a mandatory-status claim). A rule-based
extractor cannot fabricate a category or a requirement that isn't
literally suggested by the evidence text — it can only under-detect,
which is the safe failure direction for a compliance tool.

The LLM's only involvement anywhere in this pipeline is
rephrase_requirement_text() below, which improves wording for readability
— it is never asked whether a requirement exists, what category it
belongs to, or what its regulatory status is. Its rephrased output is
validated to ensure it doesn't introduce new claims (see
_looks_like_safe_rephrase) before being used, and any output that fails
that check is discarded in favor of the original rule-extracted text.

regulatory_status is intentionally always NOT_DETERMINED here: this
project's schema (Standard, StandardDocument) has no field representing a
Quality Control Order, a mandatory-certification designation, or any other
regulatory instrument (see app/schemas/compliance.py's module docstring).
A future phase that ingests real regulatory metadata is where
MANDATORY_CONFIRMED would first become possible to produce — never before
then, and never from an LLM's own claim.
"""

import re
import uuid
from dataclasses import dataclass

from app.llm.provider import LLMProvider
from app.schemas.candidate_standard import ApplicabilityStatus, CandidateStandard
from app.schemas.compliance import ComplianceRequirement, RegulatoryStatus, RequirementCategory, RequirementStatus
from app.schemas.retrieval import RetrievedChunk

# Each category maps to a set of keywords whose presence in an evidence
# chunk's text suggests that category. Purely lexical — no semantic
# judgment, no LLM. Order matters only in that the first matching category
# wins for a given chunk (a chunk mentioning both "test" and "marking"
# becomes two separate requirements, one per matched category — see
# _categories_for_text).
CATEGORY_KEYWORDS: dict[RequirementCategory, list[str]] = {
    RequirementCategory.TESTING: ["test", "tested", "testing", "sample shall be", "tested in accordance"],
    RequirementCategory.MARKING: ["marking", "shall be marked", "label", "labelled", "labeled"],
    RequirementCategory.CERTIFICATION: ["certificate", "certification", "certified", "license", "licence"],
    RequirementCategory.CONFORMITY_ASSESSMENT: ["conformity assessment", "conformity", "assessment route"],
    RequirementCategory.MANUFACTURING_QUALITY: ["quality control", "manufacturing process", "quality assurance"],
    RequirementCategory.DOCUMENTATION: [
        "technical specification",
        "drawing",
        "bill of materials",
        "test report",
        "documentation",
    ],
}

# An explicit obligation word ("shall"/"must"/"required") is the sole
# signal that a chunk states a requirement rather than background/scope
# prose — a numbered clause heading alone (e.g. "1 SCOPE") is NOT
# sufficient, since scope/introduction sections routinely carry a heading
# with no obligation at all. A requirement's clause id, when available,
# comes from the chunk's own `section` field (already populated from real
# DocumentChunk/DocumentPage data — see app/schemas/retrieval.py) rather
# than being re-derived here.
OBLIGATION_WORD_PATTERN = re.compile(r"\b(shall|must|required|requirement)\b", re.IGNORECASE)


@dataclass
class _DetectedRequirement:
    category: RequirementCategory
    chunk: RetrievedChunk


def _categories_for_text(text: str) -> list[RequirementCategory]:
    lowered = text.lower()
    return [category for category, keywords in CATEGORY_KEYWORDS.items() if any(kw in lowered for kw in keywords)]


def _chunk_states_a_requirement(chunk: RetrievedChunk) -> bool:
    return bool(OBLIGATION_WORD_PATTERN.search(chunk.text))


def _detect_requirements_in_candidate(candidate: CandidateStandard) -> list[_DetectedRequirement]:
    detected: list[_DetectedRequirement] = []
    for chunk in candidate.evidence:
        if not _chunk_states_a_requirement(chunk):
            continue
        for category in _categories_for_text(chunk.text):
            detected.append(_DetectedRequirement(category=category, chunk=chunk))
    return detected


def _default_title(category: RequirementCategory, candidate: CandidateStandard) -> str:
    label = category.value.replace("_", " ").title()
    return f"{label} requirement referenced in {candidate.document_name}"


def rephrase_requirement_text(llm_provider: LLMProvider, evidence_text: str) -> str | None:
    """Asks the LLM to rephrase already-detected evidence text into a
    clearer one-sentence description — never to decide what the
    requirement is. Returns None (caller falls back to the raw evidence
    text) if the LLM's output looks unsafe (empty, or suspiciously longer
    than a rephrase should be, suggesting it added new claims rather than
    simplifying existing ones)."""
    prompt = (
        "Rewrite the following text as ONE short, plain-language sentence describing what it requires. "
        "Do not add any information not present in the text. Do not mention standard numbers. "
        "Respond with ONLY the rewritten sentence, nothing else.\n\n"
        f"TEXT:\n{evidence_text}"
    )
    response = llm_provider.generate(system_prompt=prompt, conversation_history=[], user_message=evidence_text)
    rephrased = response.content.strip()
    if not _looks_like_safe_rephrase(rephrased, evidence_text):
        return None
    return rephrased


def _looks_like_safe_rephrase(rephrased: str, original: str) -> bool:
    if not rephrased:
        return False
    # A rephrase that is much longer than the original is more likely to
    # have added invented detail than to be a genuine simplification.
    if len(rephrased) > len(original) * 1.5 + 40:
        return False
    if "\n" in rephrased:  # a single sentence was asked for; multi-line output suggests the model went off-script
        return False
    return True


def extract_requirements(
    candidates: list[CandidateStandard], llm_provider: LLMProvider | None = None
) -> list[ComplianceRequirement]:
    """Builds ComplianceRequirement objects from candidates' evidence.
    Only candidates already marked POTENTIALLY_APPLICABLE or APPLICABLE
    (see app/product/applicability.py) contribute requirements — a
    candidate still at NEEDS_CLARIFICATION has not even been confirmed
    relevant to the product yet, so extracting a requirement from it would
    be requirement generation ahead of applicability, which the Phase 11
    brief explicitly forbids ("no unsupported requirement generation")."""
    requirements: list[ComplianceRequirement] = []
    for candidate in candidates:
        if candidate.applicability_status not in (
            ApplicabilityStatus.APPLICABLE,
            ApplicabilityStatus.POTENTIALLY_APPLICABLE,
        ):
            continue

        detected = _detect_requirements_in_candidate(candidate)
        for item in detected:
            description = item.chunk.text.strip()
            if llm_provider is not None:
                rephrased = rephrase_requirement_text(llm_provider, description)
                if rephrased:
                    description = rephrased

            status = (
                RequirementStatus.CONFIRMED
                if candidate.applicability_status == ApplicabilityStatus.APPLICABLE
                else RequirementStatus.POTENTIALLY_APPLICABLE
            )

            requirements.append(
                ComplianceRequirement(
                    id=str(uuid.uuid4()),
                    title=_default_title(item.category, candidate),
                    description=description,
                    category=item.category,
                    status=status,
                    regulatory_status=RegulatoryStatus.NOT_DETERMINED,
                    evidence=[item.chunk],
                    source_document_ids=[candidate.document_id],
                    applicable_standard_id=candidate.standard_id,
                    notes=None,
                )
            )
    return requirements

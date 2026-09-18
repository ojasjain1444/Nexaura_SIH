"""
Discovery response safety filter — Phase 10, extended in Phase 11.

Live testing against the real local model (qwen2.5:7b via Ollama)
demonstrated that prompt instructions alone are not a reliable guardrail:
even with an explicit "only discuss the candidates listed below" system
prompt (see discovery_response.py), the model fabricated IS standard
numbers that were never in the retrieved evidence, and invented an
applicability status word ("APPLIES") that doesn't exist in
ApplicabilityStatus. The underlying structured data (citations,
candidate_standards) was unaffected — only the LLM's own prose was wrong —
but that prose is exactly what the user reads.

This module is the hard guarantee the prompt alone could not provide:

  1. Fabricated standard numbers (Phase 10): scans the LLM's generated
     text for any BIS standard-number-shaped mention (reusing the same
     pattern app/ingestion/metadata_extraction.py already uses to
     recognize real IS numbers) and rejects the response if it mentions a
     standard number that isn't actually present in the retrieved evidence
     given to it for this turn.

  2. Fabricated mandatory/regulatory claims (Phase 11): no rule anywhere
     in this codebase can currently produce RegulatoryStatus.
     MANDATORY_CONFIRMED (see app/schemas/compliance.py's module
     docstring — there is no QCO/regulatory metadata to justify it yet).
     Therefore ANY mandatory-certification language in the LLM's own
     prose (e.g. "mandatory", "required by law", "compulsory
     certification") is unsafe by construction in this phase, regardless
     of context — it can only be something the model invented, since the
     structured data given to it never asserts that.

  3. Fabricated checklist items (Phase 11, discovered via live testing):
     even when the rule-based extractor correctly produced ZERO
     ComplianceRequirement items (e.g. because every candidate is still
     NEEDS_CLARIFICATION — see app/product/requirement_extraction.py's
     rule against generating requirements ahead of applicability),
     qwen2.5:7b independently invented a "Requirements Checklist" section
     naming specific requirements ("Electrical Safety Testing", "Marking
     Requirements") drawn from its own reading of the evidence rather than
     from the actual (empty) structured checklist it was given. This is
     checked by looking for requirement-category label words used as a
     list/heading construct in the response while the real requirements
     list is empty — a strong signal the model is presenting its own
     analysis as the system's structured output.

  4. Fabricated profile resolution (Phase 13, discovered via live
     testing): when app/product/specificity.py detects a genuine
     attribute conflict (e.g. "water heater" vs "water purifier") and
     produces a clarification question instead of silently picking a
     side, qwen2.5:7b was observed inventing a fictional "updated product
     profile" claiming the conflict had already been resolved in the
     new value's favor ("Category: water_purifier") — directly
     contradicting the real ProductProfile row, which correctly stayed
     unchanged. This is checked by looking for a profile-field-label
     restatement pattern (e.g. "Category:", "Product name:") in the
     response whenever a conflict question is pending for this turn — the
     LLM is never allowed to restate the profile as if a pending conflict
     were already settled.

A rejected response is replaced with a templated fallback built directly
from the structured candidates/questions/requirements — zero LLM prose,
zero risk of fabrication, for that one turn.

This is deliberately conservative (a real standard mentioned in the user's
OWN message, e.g. "is IS 302 relevant?", could also trigger check #1) —
for a compliance assistant, refusing a fluent-but-wrong answer in favor of
a mechanical-but-honest one is the correct trade-off.
"""

import re
from dataclasses import dataclass, field

from app.ingestion.metadata_extraction import STANDARD_NUMBER_PATTERN
from app.product.clarification import ClarificationQuestion
from app.schemas.candidate_standard import CandidateStandard
from app.schemas.compliance import ComplianceRequirement
from app.schemas.retrieval import RetrievedChunk

# Phase 11: mandatory/regulatory-certainty language the LLM must never
# assert on its own, because no rule in this codebase can currently
# produce RegulatoryStatus.MANDATORY_CONFIRMED — an affirmative claim using
# this language is necessarily an invention, not a report of structured
# data.
_MANDATORY_WORD_PATTERN = re.compile(
    r"\b(mandatory|compulsory|legally required|required by law|must be certified|legally compliant)\b",
    re.IGNORECASE,
)
# The model's own honest phrasing ("has not been determined", "is not
# mandatory", "not yet determined") legitimately contains a negation word
# near the mandatory-word match — checked per SENTENCE, not by a
# lookbehind immediately before the match, because phrasings like
# "Mandatory status has not been determined" put the negation word AFTER
# the mandatory-word match, not before it.
_NEGATION_WORD_PATTERN = re.compile(r"\b(not|no|never|cannot|isn't|hasn't|doesn't)\b", re.IGNORECASE)

# Phase 11: a list/heading-style mention of a requirement-category label
# (e.g. "- Electrical Safety Testing:", "**Marking Requirements:**") is
# treated as the model presenting a checklist item — only safe when the
# actual structured checklist has at least one item to point to. A bare
# mention of the word "testing" in ordinary prose (e.g. "the document
# discusses testing procedures") does NOT match this — it requires a
# list-marker or heading-like construct immediately before the category
# word, which is what a fabricated checklist entry looks like.
_CATEGORY_LABEL_WORDS = [
    "testing",
    "documentation",
    "certification",
    "conformity assessment",
    "marking",
    "manufacturing quality",
    "quality assurance",
]
_CHECKLIST_ITEM_PATTERN = re.compile(
    r"(^|\n)\s*(?:[-*•]|\d+[.)]|☐)\s*\**\s*(?:" + "|".join(_CATEGORY_LABEL_WORDS) + r")\b",
    re.IGNORECASE,
)

# Phase 13: a "Field Name: value" restatement of a ProductProfile
# attribute — e.g. "**Category:** water_purifier" or "Product name: water
# purifier". Live testing found this fabrication in TWO distinct
# situations: (a) while a conflict was genuinely pending (the LLM
# invented a resolution instead of asking), and (b) with NO conflict
# pending at all — the model simply asserted a value the real profile
# never held, unprompted. Case (b) is the more general and more dangerous
# one: it means the LLM can misstate the product profile in ordinary
# prose at any time, not only during a conflict. The fix checks EVERY
# "Field: value" restatement against the actual ProductProfile object,
# regardless of conflict status — a stated value that doesn't match the
# real field is always unsafe; a stated value that matches (or a field the
# profile has no rule/value for, e.g. genuinely restating None as
# "not specified") is fine.
_PROFILE_FIELD_LABEL_TO_ATTRIBUTE = {
    "product name": "product_name",
    "category": "product_category",
    "product type": "product_type",
    "intended use": "intended_use",
    "target market": "target_market",
    "manufacturing location": "manufacturing_location",
    "electrical characteristics": "electrical_characteristics",
    "capacity": "capacity",
    "materials": "materials",
    "technology": "technology",
    "application": "application",
}
_PROFILE_RESTATEMENT_PATTERN = re.compile(
    r"(" + "|".join(_PROFILE_FIELD_LABEL_TO_ATTRIBUTE.keys()) + r")\s*:\**\s*([^\n]+)",
    re.IGNORECASE,
)


@dataclass
class SafetyCheckResult:
    is_safe: bool
    fabricated_standard_numbers: list[str] = field(default_factory=list)
    fabricated_mandatory_claim: bool = False
    fabricated_checklist_items: bool = False
    fabricated_profile_resolution: bool = False


def _standard_numbers_in_evidence(candidates: list[CandidateStandard]) -> set[str]:
    """Every real IS number that actually appears somewhere in this turn's
    retrieved evidence or candidate document names — the only standard
    numbers the LLM is allowed to have mentioned."""
    known: set[str] = set()
    for candidate in candidates:
        for match in STANDARD_NUMBER_PATTERN.finditer(candidate.document_name):
            known.add(match.group(0).strip().upper())
        for chunk in candidate.evidence:
            for match in STANDARD_NUMBER_PATTERN.finditer(chunk.text):
                known.add(match.group(0).strip().upper())
    return known


def _contains_affirmative_mandatory_claim(text: str) -> bool:
    """True only for a sentence that asserts mandatory status without also
    negating it — "X is mandatory" is unsafe, "X has not been determined
    to be mandatory" is the honest phrasing this system itself uses and
    must not be rejected. Checked per sentence (split on '.', '!', '?')
    since a negation word later in the same sentence still applies to an
    earlier mandatory-word mention, but a negation in an unrelated
    sentence must not silently excuse a real claim elsewhere."""
    for sentence in re.split(r"[.!?]", text):
        if _MANDATORY_WORD_PATTERN.search(sentence) and not _NEGATION_WORD_PATTERN.search(sentence):
            return True
    return False


def _values_disagree(stated: str, actual: str) -> bool:
    """True if a stated value looks like a genuinely different claim from
    the actual field value — case/whitespace-insensitive equality, and a
    substring check in either direction (so "water heater" stated against
    an actual "water_heater" — or the reverse — is NOT flagged; those are
    the same fact in different spelling, not a fabrication)."""
    stated_norm = stated.strip().strip("*").strip().lower()
    actual_norm = actual.strip().lower()
    if not stated_norm or not actual_norm:
        return False
    if stated_norm == actual_norm:
        return False
    normalized_stated = stated_norm.replace("_", " ")
    normalized_actual = actual_norm.replace("_", " ")
    if normalized_stated == normalized_actual:
        return False
    if normalized_stated in normalized_actual or normalized_actual in normalized_stated:
        return False
    return True


def _contains_fabricated_profile_restatement(llm_text: str, profile) -> bool:
    """True if llm_text restates any ProductProfile field ("Category:
    water_purifier") with a value that disagrees with the field's actual
    current value on the real profile object. Checked unconditionally —
    NOT only when a conflict is pending — because live testing found the
    LLM can misstate the profile in ordinary prose even with no conflict
    in play (see module docstring, case #4). A field the profile has no
    value for (None) is not checked here — there's nothing to disagree
    with yet, and the LLM restating "not specified"/"unknown" for an
    unset field is not a fabrication."""
    if profile is None:
        return False
    for match in _PROFILE_RESTATEMENT_PATTERN.finditer(llm_text):
        label, stated_value = match.group(1).lower(), match.group(2)
        attribute = _PROFILE_FIELD_LABEL_TO_ATTRIBUTE.get(label)
        if attribute is None:
            continue
        actual_value = getattr(profile, attribute, None)
        if actual_value is None:
            continue
        if _values_disagree(stated_value, actual_value):
            return True
    return False


def check_response_safety(
    llm_text: str,
    candidates: list[CandidateStandard],
    requirements: list[ComplianceRequirement] | None = None,
    profile=None,
) -> SafetyCheckResult:
    """Returns is_safe=False if llm_text mentions any IS-number-shaped
    standard reference that isn't actually backed by this turn's evidence,
    uses mandatory/regulatory-certainty language that no structured
    requirement in this phase can ever actually support, presents
    checklist-style requirement items while the real structured
    `requirements` list is empty (see module docstring, case #3), or
    restates any ProductProfile field with a value that disagrees with the
    field's actual current value on `profile` (case #4) — checked
    unconditionally whenever `profile` is given, not only during a
    pending conflict (see _contains_fabricated_profile_restatement)."""
    known_numbers = _standard_numbers_in_evidence(candidates)
    mentioned = {match.group(0).strip().upper() for match in STANDARD_NUMBER_PATTERN.finditer(llm_text)}
    fabricated_numbers = sorted(mentioned - known_numbers)

    fabricated_mandatory_claim = _contains_affirmative_mandatory_claim(llm_text)

    fabricated_checklist_items = not requirements and bool(_CHECKLIST_ITEM_PATTERN.search(llm_text))

    fabricated_profile_resolution = _contains_fabricated_profile_restatement(llm_text, profile)

    return SafetyCheckResult(
        is_safe=(
            len(fabricated_numbers) == 0
            and not fabricated_mandatory_claim
            and not fabricated_checklist_items
            and not fabricated_profile_resolution
        ),
        fabricated_standard_numbers=fabricated_numbers,
        fabricated_mandatory_claim=fabricated_mandatory_claim,
        fabricated_checklist_items=fabricated_checklist_items,
        fabricated_profile_resolution=fabricated_profile_resolution,
    )


# Recognizes a standard number inside a source filename, where the separators
# are underscores or dots rather than spaces: IS_456_2000.pdf,
# gov.in.is.302.2.201.2008.pdf. STANDARD_NUMBER_PATTERN requires whitespace
# after "IS" and so matches neither, which left document names contributing
# nothing at all to the set of known standards.
_FILENAME_STANDARD_PATTERN = re.compile(r"(?:^|[^a-z0-9])is[._\-\s]*(\d{2,6})", re.IGNORECASE)


def _standard_key(raw: str) -> str:
    """Reduces a standard mention to its base number for comparison.

    Everything after the base number — year of publication, part and section
    numbers — is dropped, so "IS 456", "IS 456:2000", "IS456" and
    "IS 456-2000" are all the same standard. Deliberately lenient: the cost
    of missing a fabrication is one bad sentence, while the cost of a false
    positive is discarding an entire correct answer.
    """
    digits = re.search(r"\d{2,6}", raw)
    return digits.group(0) if digits else " ".join(raw.upper().split())


def _standard_keys_in(text: str) -> set[str]:
    keys = {_standard_key(m.group(0)) for m in STANDARD_NUMBER_PATTERN.finditer(text)}
    keys.update(m.group(1) for m in _FILENAME_STANDARD_PATTERN.finditer(text))
    return keys


def check_plain_chat_response_safety(llm_text: str, retrieved_chunks: list[RetrievedChunk]) -> list[str]:
    """The plain (non-product-discovery) BIS Q&A chat path has real
    grounded retrieval but, until now, no fabrication check on the LLM's
    own generated prose — confirmed via live testing to be a real gap:
    the same qwen2.5:7b model that discovery mode already had to guard
    against invented a standard number ("IS 14587:1998") in a plain-chat
    answer that was never actually in the retrieved evidence. Only check
    #1 from this module's docstring (fabricated standard numbers) applies
    here — the mandatory/checklist/profile-resolution checks are all
    product-discovery-specific concepts (RegulatoryStatus, ComplianceRequirement,
    ProductProfile) that plain chat has no equivalent of. Returns the list
    of fabricated standard numbers found (empty = safe) rather than a
    SafetyCheckResult, since none of that dataclass's other fields apply.

    Comparison is on the standard's base number only (see _standard_key).
    Matching the raw matched text was wrong: evidence says "IS 456" while an
    answer naturally writes "IS 456:2000", and a set difference over those
    raw strings flagged the correctly-cited standard as fabricated — which
    discarded almost every real answer."""
    known_numbers: set[str] = set()
    for chunk in retrieved_chunks:
        known_numbers.update(_standard_keys_in(chunk.document_name))
        known_numbers.update(_standard_keys_in(chunk.text))

    mentioned: dict[str, str] = {}
    for match in STANDARD_NUMBER_PATTERN.finditer(llm_text):
        raw = match.group(0).strip()
        key = _standard_key(raw)
        if key not in known_numbers:
            mentioned.setdefault(key, " ".join(raw.split()))

    return sorted(mentioned.values())


# Openings of the "but here is what you would generally need" continuation
# that follows an otherwise correct "not covered" answer. Live testing with
# qwen2.5:7b showed the prompt cannot reliably suppress this: told
# explicitly to stop after saying a topic was not covered, the model still
# went on to invent BIS marks and testing laboratories. Cutting the
# continuation mechanically is what makes the refusal hold.
_SPECULATION_OPENERS = (
    "to obtain",
    "to get",
    "typically",
    "generally",
    "in general",
    "you would typically",
    "you would generally",
    "you would need",
    "you will need",
    "you may want",
    "you should",
    "it is recommended",
    "i recommend",
    "for a comprehensive",
    "to provide a comprehensive",
    "however, for",
    "the process would",
    "the general process",
    "common standards",
    "relevant standards",
    "applicable standards",
    "some relevant",
    "these standards",
    "to ensure compliance",
    "if you need detailed",
    "you would need to refer",
    "you may refer",
    "please refer",
    "refer to",
    "consult",
    "if you need information",
    "if you are looking",
    "if you need more",
    "if you require",
    "if you have questions about bis standards for",
    "for detailed",
    "for more detailed",
    "for a detailed",
    "for information on",
    "for wooden",
    "for electric",
    "for laptops",
    "for shampoo",
    "for these",
    "for such",
    "for your",
    "for the certification",
    "the relevant standard",
    "the applicable standard",
    "you can check",
    "you might",
    "i suggest",
    "i would suggest",
    "it would be advisable",
    "it is advisable",
    "commonly",
    "usually",
    "normally",
    "laptops are",
    "these are governed",
    "they are governed",
    "such products are",
)

# Bodies and schemes outside the corpus. A sentence that reaches for one is
# supplying a remembered fact regardless of how it is introduced, so it is
# cut even when it does not begin with a speculation opener.
_EXTERNAL_AUTHORITY_PATTERN = re.compile(
    r"\b(?:IEC|ISO|IEEE|UL|ANSI|ASTM|EN|BS|DIN|JIS|CE\s+mark|FCC|NABL|CPSC)\b"
)


def trim_off_corpus_speculation(llm_text: str) -> str:
    """Cuts an off-corpus answer at the point it stops reporting what the
    evidence says and starts supplying remembered facts.

    Only used when retrieval has already been judged off-corpus, where the
    correct answer is "the documents do not cover this" and everything after
    it — suggested standards, certification steps, laboratory names — is by
    construction invented. The model produces that continuation anyway, so it
    is removed here rather than asked for politely.

    Works a sentence at a time, not a paragraph at a time: the pivot usually
    happens mid-paragraph, in the sentence right after the refusal ("... does
    not cover this. For wooden chairs you would typically refer to ...").
    """
    text = llm_text.strip()
    if not text:
        return llm_text

    # Split on sentence ends and on list-item boundaries, keeping separators
    # so the kept prefix can be reassembled exactly as written.
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    pieces = [p for p in pieces if p.strip()]

    kept: list[str] = []
    for piece in pieces:
        probe = piece.strip().lower().lstrip("*-•#0123456789. )")
        is_list_item = bool(re.match(r"^\s*(?:\d+[.)]|[-*•])\s+", piece))
        # A list is speculative when it enumerates steps or standards the
        # evidence does not support, but the same shape is used for the
        # legitimate summary of what the corpus does contain. The lead-in
        # right before it says which one this is.
        if kept and (
            probe.startswith(_SPECULATION_OPENERS)
            or _EXTERNAL_AUTHORITY_PATTERN.search(piece)
            or (is_list_item and not _introduces_corpus_summary(kept))
        ):
            break
        kept.append(piece)

    if len(kept) == len(pieces):
        return text

    trimmed = " ".join(k.strip() for k in kept).strip()
    return (
        f"{trimmed}\n\n"
        "I've stopped there rather than name standards, laboratories or steps that aren't in these documents. "
        "If the relevant standard is added to the corpus, I can answer this properly."
    )


# Lead-ins that introduce a list of what the retrieved documents actually
# contain. A list under one of these is grounded and must survive the trim.
_CORPUS_SUMMARY_LEAD_INS = (
    "do cover",
    "does cover",
    "do contain",
    "does contain",
    "are about",
    "is about",
    "relate to",
    "relates to",
    "pertain to",
    "pertains to",
    "cover the following",
    "contain the following",
    "include the following",
    "includes the following",
    "the documents provided",
    "the retrieved content",
    "the retrieved documents",
    "what they do cover",
)


def _introduces_corpus_summary(kept: list[str]) -> bool:
    """True when the sentence immediately before a list announces what the
    corpus does contain, rather than pivoting to invented guidance."""
    if not kept:
        return False
    return any(lead in kept[-1].lower() for lead in _CORPUS_SUMMARY_LEAD_INS)


def append_unverified_standards_warning(llm_text: str, fabricated_numbers: list[str]) -> str:
    """Flags standard numbers the evidence does not support, keeping the rest
    of the answer.

    Preferred over build_plain_chat_fallback_response for plain chat: one
    unsupported number used to discard the entire response, including
    correctly cited material, and the replacement text answered nothing at
    all. Naming the suspect numbers keeps the useful content readable while
    still telling the user exactly what to distrust."""
    numbers = ", ".join(fabricated_numbers)
    plural = "s" if len(fabricated_numbers) > 1 else ""
    return (
        f"{llm_text.rstrip()}\n\n"
        f"⚠️ Unverified: this answer mentions {numbers}, which do{'' if plural else 'es'} not appear in the "
        f"documents retrieved for your question. Treat that reference{plural} as unconfirmed and check it "
        f"against the official BIS catalogue before relying on it."
    )


def build_plain_chat_fallback_response(retrieved_chunks: list[RetrievedChunk]) -> str:
    """Zero-LLM-prose fallback for the plain chat path, used when
    check_plain_chat_response_safety finds a fabricated standard number.
    Mirrors build_fallback_response's "mechanical but honest" trade-off
    (module docstring) for the plain-chat case: lists the real documents
    actually retrieved this turn rather than repeating the LLM's
    (rejected) prose."""
    if not retrieved_chunks:
        return (
            "I don't have any retrieved evidence to answer this from. Please try rephrasing your question, "
            "or make sure a relevant document has been ingested."
        )

    seen_documents: dict[str, None] = {}
    for chunk in retrieved_chunks:
        seen_documents.setdefault(chunk.document_name, None)

    lines = [
        "I found a response that referenced a standard not present in the retrieved evidence, so I'm not "
        "showing it. Here is what was actually retrieved for this question:",
        "",
    ]
    lines.extend(f"- {name}" for name in seen_documents)
    return "\n".join(lines)


def build_fallback_response(
    questions: list[ClarificationQuestion],
    candidates: list[CandidateStandard],
    requirements: list[ComplianceRequirement] | None = None,
) -> str:
    """A zero-LLM-prose response built directly from structured data, used
    when the LLM's own response fails the safety check. Mechanical but
    guaranteed to contain no fabricated standard numbers, invented
    applicability claims, or invented mandatory-status claims."""
    lines: list[str] = []

    if questions:
        lines.append("To help identify relevant requirements, could you clarify:")
        lines.extend(f"{i}. {q.question}" for i, q in enumerate(questions, start=1))

    if candidates:
        if lines:
            lines.append("")
        lines.append("Based on retrieved evidence so far:")
        for candidate in candidates:
            status_label = candidate.applicability_status.value.replace("_", " ").title()
            lines.append(f"- {candidate.document_name}: {status_label} — {candidate.applicability_reason}")
    elif not questions:
        lines.append(
            "I don't have enough retrieved evidence yet to identify a candidate standard for this product. "
            "Please provide more product details or ensure relevant documents are indexed."
        )

    if requirements:
        lines.append("")
        lines.append("Potential requirements identified from retrieved evidence:")
        for req in requirements:
            category_label = req.category.value.replace("_", " ").title()
            status_label = req.status.value.replace("_", " ").title()
            lines.append(f"- [{category_label}] {req.title} ({status_label})")
        lines.append("")
        lines.append(
            "Mandatory/regulatory status could not be determined from available evidence for any of the above."
        )

    return "\n".join(lines)

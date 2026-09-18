"""
Product profile extraction — Phase 10, extended in Phase 12.

Converts a user's free-text message into structured ProductProfile field
updates. No LLM provider in this project has a structured-output/JSON mode
(see app/llm/provider.py — generate() returns plain prose only), so this
module cannot simply trust an LLM to emit valid JSON. Instead:

  1. The LLM is asked to respond in a small, constrained line-based format
     ("field: value", one per line — see EXTRACTION_PROMPT).
  2. parse_extraction_output() strictly validates that output: any line
     whose field name is not in ProductProfile.EXTRACTABLE_FIELDS is
     dropped silently, never stored. A field whose value is empty/"unknown"/
     "not specified" is treated as no information, not a guess.
  3. apply_updates() only ever overwrites a field that is currently None —
     an already-answered attribute is never silently replaced by a later,
     possibly-lower-confidence extraction. This is what makes "don't
     unnecessarily re-request answered fields" hold at the data layer, not
     just in the clarification-question layer.

The LLM is never the authority on what counts as a valid field — the
allow-list in ProductProfile.EXTRACTABLE_FIELDS is.

Phase 12 adds normalization for product_category (and, once a category is
known, intended_use/product_type) BEFORE storage — see
app/product/product_taxonomy.py's module docstring for the Phase 10
incident this fixes (an LLM extracting "household appliances" instead of
the exact seeded key "water_heater" silently broke category-specific
clarification). Normalization happens in apply_updates(), not
parse_extraction_output(): the parser's job stays "is this a valid field
name with real content," or normalization's job is "map this content to a
controlled vocabulary" — two different concerns. When normalization can't
confidently map a value, the raw LLM text is stored as-is (never
discarded) — clarification.py's existing CATEGORY_QUESTIONS.get(...,
FALLBACK_QUESTIONS) already handles an unmatched category honestly by
falling back to generic questions.

Phase 13 replaces the strict "never touch an already-set field" rule with
app/product/specificity.py's deterministic decision for the two fields
that have an objective specificity/conflict rule (product_category,
intended_use) — see that module's docstring for the Phase 12 incident
this fixes (a vague first answer like "appliance" could never be improved
by a later, clearer one). Every other field keeps the original Phase 10
first-write-wins behavior unchanged.
"""

import re

from app.llm.provider import LLMProvider
from app.models.product_profile import ProductProfile
from app.product.product_taxonomy import normalize_category, normalize_intended_use, normalize_water_heater_type
from app.product.specificity import UpdateDecision, evaluate_update

_UNKNOWN_VALUES = {"", "unknown", "not specified", "n/a", "none", "not mentioned", "not provided"}

EXTRACTION_PROMPT = """You are extracting structured product attributes from a user's message, for a BIS compliance assistant.

Respond with ONLY plain lines in the exact form:
field_name: value

Use only these field names, one per line, only when the message actually states that attribute:
product_name, product_category, product_type, intended_use, target_market, manufacturing_location, electrical_characteristics, capacity, materials, technology, application, other_attributes

Rules:
- Do not include a field if the message does not mention it.
- Do not guess or infer a value that was not stated.
- Do not invent technical specifications.
- Do not add any explanation, heading, or text other than the field lines.
- If nothing extractable is present, respond with exactly: (none)"""

_LINE_PATTERN = re.compile(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", re.IGNORECASE)


def parse_extraction_output(raw_output: str) -> dict[str, str]:
    """Strictly parses the LLM's line-based extraction output into a dict
    of {field: value}. Any field not in ProductProfile.EXTRACTABLE_FIELDS
    is dropped. Any value that reads as "no information" (empty, "unknown",
    "not specified", etc.) is dropped rather than stored as a literal
    string. This is the sole gate between free-form LLM prose and the
    database — nothing downstream re-validates field names."""
    updates: dict[str, str] = {}
    for line in raw_output.splitlines():
        match = _LINE_PATTERN.match(line)
        if not match:
            continue
        field, value = match.group(1).strip().lower(), match.group(2).strip()
        if field not in ProductProfile.EXTRACTABLE_FIELDS:
            continue
        if value.lower() in _UNKNOWN_VALUES:
            continue
        updates[field] = value
    return updates


def _normalize_field(field: str, value: str, profile: ProductProfile) -> str:
    """Maps a field's raw extracted value to a controlled vocabulary where
    Phase 12 defines one. Returns the raw value unchanged when no
    normalization applies to this field, or when normalization can't
    confidently map it — never discards information, only ever replaces it
    with a more useful controlled equivalent when confident."""
    if field == "product_category":
        return normalize_category(value) or value

    # intended_use/product_type normalization only applies once a category
    # is known that actually uses these controlled values — normalizing
    # them for an unrecognized category would impose a vocabulary the
    # category's own clarification questions don't expect.
    category = profile.product_category
    if field == "intended_use" and category == "water_heater":
        return normalize_intended_use(value) or value
    if field == "product_type" and category == "water_heater":
        return normalize_water_heater_type(value) or value

    return value


def apply_updates(profile: ProductProfile, updates: dict[str, str]) -> tuple[list[str], list[str]]:
    """Applies validated updates to a ProductProfile. Returns
    (changed_fields, clarification_questions).

    For a field with no field is currently None, the value is always
    filled (unchanged Phase 10 behavior). For an already-set field:
      - product_category and intended_use consult
        app/product/specificity.py's deterministic decision — REPLACE
        (confidently more specific, e.g. "appliance" -> "water_heater"),
        KEEP_EXISTING (no real change, or the new value is vaguer), or
        NEEDS_CLARIFICATION (a genuine conflict between two controlled
        values — neither silently wins; a clarification question is
        returned instead of being asked/answered here).
      - every other field keeps the original Phase 10 rule: an
        already-set value is never touched.

    product_category is processed before any other field in this same
    call, so intended_use/product_type normalization below can see the
    (possibly just-set/just-replaced) category."""
    changed: list[str] = []
    clarification_questions: list[str] = []
    ordered_fields = sorted(updates, key=lambda f: 0 if f == "product_category" else 1)
    for field in ordered_fields:
        raw_value = updates[field]
        current_value = getattr(profile, field)

        if current_value is None:
            setattr(profile, field, _normalize_field(field, raw_value, profile))
            changed.append(field)
            continue

        # evaluate_update() receives the RAW value, not the pre-normalized
        # one: normalize_category() is not idempotent across its own
        # output (e.g. normalize_category("water heater") == "water_heater",
        # but normalize_category("water_heater") == None — the synonym
        # list uses spaces, the controlled key uses underscores). Passing
        # an already-normalized value back through normalize_category() a
        # second time would silently un-recognize it. specificity.py does
        # its own single normalization pass on each raw value it's given.
        result = evaluate_update(field, current_value, raw_value)
        if result.decision == UpdateDecision.REPLACE:
            setattr(profile, field, _normalize_field(field, raw_value, profile))
            changed.append(field)
        elif result.decision == UpdateDecision.NEEDS_CLARIFICATION and result.clarification_question:
            clarification_questions.append(result.clarification_question)
        # KEEP_EXISTING: silently ignored, matching Phase 10's original
        # "first stated value wins" behavior for a non-improving update.

    return changed, clarification_questions


def extract_profile_updates(llm_provider: LLMProvider, user_message: str) -> dict[str, str]:
    """Runs the LLM extraction step and returns strictly validated updates.
    Uses the LLM only as a text-understanding tool — the actual authority
    over what gets stored is parse_extraction_output()'s allow-list, per
    this module's docstring."""
    response = llm_provider.generate(system_prompt=EXTRACTION_PROMPT, conversation_history=[], user_message=user_message)
    return parse_extraction_output(response.content)

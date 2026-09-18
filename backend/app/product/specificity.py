"""
Product-profile update specificity — Phase 13.

Fixes a confirmed gap in app/product/profile_extraction.py's
apply_updates(): the sole write condition was
"if getattr(profile, field) is None" — an already-answered field could
NEVER be replaced, even by a later, more specific/correct value. Example
(observed live against qwen2.5:7b in Phase 12 testing): turn 1 extracts
product_category="appliance" (no taxonomy match); turn 2's much clearer
"domestic electric storage water heater" could never override it, because
the field was already non-None.

This module is a small, deterministic decision function —
may_replace_value() — used only for fields where "specificity" has an
objective, testable meaning via the existing Phase 12 controlled taxonomy
(app/product/product_taxonomy.py). It does NOT let an LLM decide when to
overwrite a field; it decides using the same taxonomy-membership check
Phase 12 already established, extended with one more rule: a genuine
category CONFLICT (old and new both normalize to a controlled category,
but to DIFFERENT ones) is never silently resolved either way — it is
surfaced as NEEDS_CLARIFICATION instead, per the explicit Phase 13
instruction "where conflict is genuinely ambiguous, NEEDS_CLARIFICATION
rather than guessing."

Only product_category and intended_use are given specificity/conflict
rules here — the same two attributes Phase 12 already normalizes (see
product_taxonomy.py's own "deliberately limited... not a general
unit-parsing system" precedent). Every other ProductProfile field keeps
Phase 10's original first-write-wins behavior, since there is no
comparably objective specificity signal for those without inventing one.
"""

from dataclasses import dataclass
from enum import Enum

from app.product.product_taxonomy import CONTROLLED_CATEGORIES, normalize_category, normalize_intended_use


class UpdateDecision(str, Enum):
    KEEP_EXISTING = "KEEP_EXISTING"  # new value adds no information over the current one
    REPLACE = "REPLACE"  # new value is confidently more specific/correct — safe to overwrite
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"  # old and new conflict and neither is objectively more specific


@dataclass
class SpecificityResult:
    decision: UpdateDecision
    # Only set when decision == NEEDS_CLARIFICATION — a ready-to-ask
    # question surfacing the detected conflict honestly, never silently
    # picking a side.
    clarification_question: str | None = None


def _category_specificity_decision(current: str, new: str) -> SpecificityResult:
    current_normalized = normalize_category(current)
    new_normalized = normalize_category(new)

    # New value maps to a controlled category the old one didn't reach —
    # objectively more specific by the same taxonomy Phase 12 already
    # trusts. This is the exact Phase 12 incident's fix.
    if new_normalized and not current_normalized:
        return SpecificityResult(UpdateDecision.REPLACE)

    # Old value was already a controlled category; new value isn't (or is
    # a plain repeat) — never let a vaguer restatement downgrade an
    # already-specific answer.
    if current_normalized and not new_normalized:
        return SpecificityResult(UpdateDecision.KEEP_EXISTING)

    # Both map to controlled categories. Same category (possibly phrased
    # differently) -> no real change. Different categories -> a genuine
    # conflict; the taxonomy alone cannot say which one is correct, so
    # this must be asked, not guessed.
    if current_normalized and new_normalized:
        if current_normalized == new_normalized:
            return SpecificityResult(UpdateDecision.KEEP_EXISTING)
        return SpecificityResult(
            UpdateDecision.NEEDS_CLARIFICATION,
            clarification_question=(
                f"Earlier you described this as a {current_normalized.replace('_', ' ')}, but this message "
                f"suggests a {new_normalized.replace('_', ' ')}. Which is correct?"
            ),
        )

    # Neither value maps to a controlled category — no specificity signal
    # either way. Keep the first-stated value (Phase 10's original rule)
    # rather than churn on two equally-vague restatements.
    return SpecificityResult(UpdateDecision.KEEP_EXISTING)


def _intended_use_conflict_decision(current: str, new: str) -> SpecificityResult:
    current_normalized = normalize_intended_use(current)
    new_normalized = normalize_intended_use(new)

    if new_normalized and not current_normalized:
        return SpecificityResult(UpdateDecision.REPLACE)
    if current_normalized and new_normalized and current_normalized != new_normalized:
        # This is a genuine attribute conflict (Phase 13 brief's "domestic"
        # -> "commercial" example), not a specificity improvement — a
        # controlled value being replaced by a DIFFERENT controlled value
        # is exactly the ambiguous case that must not be silently resolved.
        return SpecificityResult(
            UpdateDecision.NEEDS_CLARIFICATION,
            clarification_question=(
                f"Earlier you said this was for {current_normalized} use, but this message suggests "
                f"{new_normalized} use. Which is correct?"
            ),
        )
    return SpecificityResult(UpdateDecision.KEEP_EXISTING)


# Fields with a defined specificity/conflict rule. Any field not in this
# dict keeps app/product/profile_extraction.py's original first-write-wins
# behavior unchanged — see module docstring for why this isn't extended to
# every field.
_SPECIFICITY_RULES = {
    "product_category": _category_specificity_decision,
    "intended_use": _intended_use_conflict_decision,
}


def evaluate_update(field: str, current_value: str, new_value: str) -> SpecificityResult:
    """Decides whether a new value for an already-set field should replace
    it, be discarded, or raise a clarification question. Only called when
    current_value is not None (the None case is still a plain first-write,
    handled by apply_updates() itself, not this module)."""
    rule = _SPECIFICITY_RULES.get(field)
    if rule is None:
        return SpecificityResult(UpdateDecision.KEEP_EXISTING)
    if current_value == new_value:
        return SpecificityResult(UpdateDecision.KEEP_EXISTING)
    return rule(current_value, new_value)

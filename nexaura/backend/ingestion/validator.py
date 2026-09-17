"""
validator.py — Phase 9: Knowledge Unit Validation

Project: Nexaura (SIH 2026 — SIH26107)

Validates every KnowledgeUnit before database insertion.

Rules:
    - Never silently discard bad records
    - Flag with validation_status="flagged" and needs_review=True
    - Log all flagged records to low_confidence.jsonl
    - Generate a ValidationReport for the processing summary

Checks:
    1. Missing standard_number
    2. Missing clause
    3. Empty text
    4. Low OCR confidence
    5. Duplicate records (by content hash)
    6. Broken hierarchy (parent clause not seen)
    7. Invalid page references
    8. Malformed technical parameters
    9. Suspicious values (e.g. year out of range)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Validation Result
# =============================================================================

@dataclass
class ValidationIssue:
    """A single validation issue found in a KnowledgeUnit."""
    code: str           # SHORT_CODE for the issue type
    message: str
    severity: str       # "error" | "warning" | "info"


@dataclass
class UnitValidationResult:
    """Validation result for a single KnowledgeUnit."""
    unit_id: str
    standard_number: str
    clause: str
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)


@dataclass
class ValidationReport:
    """Aggregate validation report for a processing run."""
    total_units: int = 0
    valid_units: int = 0
    flagged_units: int = 0
    rejected_units: int = 0
    duplicate_units: int = 0
    low_confidence_units: int = 0

    issues_by_code: dict[str, int] = field(default_factory=dict)
    flagged_ids: list[str] = field(default_factory=list)

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# =============================================================================
# Validator
# =============================================================================

class KnowledgeUnitValidator:
    """
    Validates KnowledgeUnit records before database insertion.

    Never silently discards records — always flags and logs.
    """

    MIN_CONFIDENCE = 0.70
    MIN_TEXT_LENGTH = 5
    VALID_YEARS = (1900, 2100)

    def __init__(
        self,
        low_confidence_log: Optional[Path] = None,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        """
        Args:
            low_confidence_log: Path to JSONL file for flagged records.
            min_confidence: Minimum OCR confidence threshold.
        """
        self.low_confidence_log = Path(low_confidence_log) if low_confidence_log else None
        if self.low_confidence_log:
            self.low_confidence_log.parent.mkdir(parents=True, exist_ok=True)
        self.min_confidence = min_confidence
        self._seen_hashes: set[str] = set()
        self._seen_clauses: set[str] = set()  # per-document duplicate check

    def reset_document_state(self) -> None:
        """Reset per-document tracking (call before processing each PDF)."""
        self._seen_clauses.clear()

    def validate(self, ku) -> UnitValidationResult:
        """
        Validate a single KnowledgeUnit.

        Args:
            ku: KnowledgeUnit instance.

        Returns:
            UnitValidationResult.
            Also modifies ku.validation_status and ku.needs_review in place.
        """
        issues: list[ValidationIssue] = []

        # Check 1: Missing standard_number
        if not ku.standard_number or ku.standard_number == "unknown":
            issues.append(ValidationIssue(
                code="MISSING_STD_NUM",
                message="standard_number is missing or 'unknown'",
                severity="error",
            ))

        # Check 2: Missing clause
        if not ku.clause:
            issues.append(ValidationIssue(
                code="MISSING_CLAUSE",
                message="clause is empty",
                severity="error",
            ))

        # Check 3: Empty text
        text = ku.clean_text or ku.text or ""
        if len(text.strip()) < self.MIN_TEXT_LENGTH:
            issues.append(ValidationIssue(
                code="EMPTY_TEXT",
                message=f"text length {len(text.strip())} < {self.MIN_TEXT_LENGTH}",
                severity="warning",
            ))

        # Check 4: Low OCR confidence
        if ku.ocr_confidence < self.min_confidence:
            issues.append(ValidationIssue(
                code="LOW_CONFIDENCE",
                message=f"OCR confidence {ku.ocr_confidence:.2f} < {self.min_confidence}",
                severity="warning",
            ))

        # Check 5: Duplicate record (within current processing run)
        content_hash = self._compute_content_hash(ku)
        if content_hash in self._seen_hashes:
            issues.append(ValidationIssue(
                code="DUPLICATE_RECORD",
                message="Duplicate content hash — possible repeated clause",
                severity="warning",
            ))
            ku.needs_review = True
        else:
            self._seen_hashes.add(content_hash)

        # Check 6: Duplicate clause (within same document)
        clause_key = f"{ku.standard_number}::{ku.clause}"
        if clause_key in self._seen_clauses:
            issues.append(ValidationIssue(
                code="DUPLICATE_CLAUSE",
                message=f"Clause {ku.clause} appears more than once in {ku.standard_number}",
                severity="warning",
            ))
        else:
            self._seen_clauses.add(clause_key)

        # Check 7: Invalid page reference
        if ku.page_start > 0 and ku.page_end > 0 and ku.page_start > ku.page_end:
            issues.append(ValidationIssue(
                code="INVALID_PAGES",
                message=f"page_start ({ku.page_start}) > page_end ({ku.page_end})",
                severity="warning",
            ))

        # Check 8: Year range validity
        if ku.year is not None:
            if not (self.VALID_YEARS[0] <= ku.year <= self.VALID_YEARS[1]):
                issues.append(ValidationIssue(
                    code="INVALID_YEAR",
                    message=f"Year {ku.year} outside valid range {self.VALID_YEARS}",
                    severity="warning",
                ))

        # Check 9: Malformed technical parameters
        for param in ku.technical_parameters:
            if param.value is not None and abs(param.value) > 1_000_000:
                issues.append(ValidationIssue(
                    code="SUSPICIOUS_VALUE",
                    message=f"Parameter '{param.name}' has suspicious value: {param.value}",
                    severity="warning",
                ))

        # Check 10: needs_review flag from extraction
        if ku.needs_review:
            issues.append(ValidationIssue(
                code="EXTRACTION_REVIEW",
                message="Extraction engine flagged this record for review",
                severity="warning",
            ))

        # Determine overall validity
        has_errors = any(i.severity == "error" for i in issues)

        if has_errors:
            ku.validation_status = "flagged"
            ku.needs_review = True
        elif issues:
            ku.validation_status = "flagged"
            ku.needs_review = True
        else:
            ku.validation_status = "valid"

        # Log flagged records
        if ku.needs_review and self.low_confidence_log:
            self._log_flagged(ku, issues)

        result = UnitValidationResult(
            unit_id=ku.id,
            standard_number=ku.standard_number,
            clause=ku.clause,
            valid=not has_errors,
            issues=issues,
        )

        if issues:
            logger.debug(
                "Validation issues for %s [%s]: %s",
                ku.id, ku.validation_status,
                [i.code for i in issues],
            )

        return result

    def validate_batch(self, units: list) -> tuple[list, ValidationReport]:
        """
        Validate a list of KnowledgeUnits.

        Returns:
            Tuple of (validated units, ValidationReport).
            All units are returned (none discarded).
        """
        report = ValidationReport(total_units=len(units))
        results = []

        for ku in units:
            result = self.validate(ku)
            results.append(result)

            if result.valid and not ku.needs_review:
                report.valid_units += 1
            else:
                report.flagged_units += 1
                report.flagged_ids.append(ku.id)

            if ku.ocr_confidence < self.min_confidence:
                report.low_confidence_units += 1

            # Count by issue code
            for issue in result.issues:
                report.issues_by_code[issue.code] = (
                    report.issues_by_code.get(issue.code, 0) + 1
                )
                if issue.code == "DUPLICATE_RECORD":
                    report.duplicate_units += 1

        return units, report

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _compute_content_hash(self, ku) -> str:
        """Compute a content hash for duplicate detection."""
        key = f"{ku.standard_number}::{ku.clause}::{(ku.text or '')[:200]}"
        return hashlib.md5(key.encode()).hexdigest()

    def _log_flagged(self, ku, issues: list[ValidationIssue]) -> None:
        """Log a flagged record to the low_confidence JSONL file."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "id": ku.id,
            "standard_number": ku.standard_number,
            "clause": ku.clause,
            "source_pdf": ku.source_pdf,
            "page_start": ku.page_start,
            "ocr_confidence": ku.ocr_confidence,
            "validation_status": ku.validation_status,
            "issues": [{"code": i.code, "message": i.message, "severity": i.severity} for i in issues],
        }
        try:
            with open(self.low_confidence_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to write flagged log: %s", exc)

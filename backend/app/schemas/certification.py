"""
API schemas for CertificationScheme, matching src/types/standards.ts's
CertificationScheme / CertificationStep field names.
"""

from pydantic import BaseModel, Field


class CertificationStepResponse(BaseModel):
    order: int
    title: str
    description: str


class CertificationSchemeResponse(BaseModel):
    id: str
    name: str
    type: str
    summary: str
    eligibility: list[str]
    steps: list[CertificationStepResponse]
    average_duration_days: int = Field(serialization_alias="averageDurationDays")
    fees: str

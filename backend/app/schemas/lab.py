"""
API schemas for Lab, matching src/types/standards.ts's TestingLab.

`distanceKm` is included as an optional field for frontend type
compatibility but is always null from this backend — see
app/models/lab.py for why it is not a stored/computed value in this phase.
"""

from pydantic import BaseModel, Field


class LabResponse(BaseModel):
    id: str
    name: str
    city: str
    state: str
    accreditations: list[str]
    test_categories: list[str] = Field(serialization_alias="testCategories")
    contact: str
    distance_km: float | None = Field(default=None, serialization_alias="distanceKm")

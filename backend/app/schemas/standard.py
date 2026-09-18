"""
API schemas for Standard.

Field names use camelCase aliases to match the frontend's IndianStandard
type (src/types/standards.ts) exactly, so src/services/api.ts can pass the
JSON response straight through without a field-renaming adapter step.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class StandardResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    code: str
    title: str
    category: str
    description: str
    status: str
    last_amended: date = Field(serialization_alias="lastAmended")
    sector: str
    related_codes: list[str] = Field(serialization_alias="relatedCodes")

"""
ProductProfileResponse — Phase 10, moved to its own module in Phase 11 to
avoid a circular import between app/schemas/chat.py (which returns a
ProductProfileResponse on ChatResponse) and app/schemas/compliance.py
(whose ComplianceChecklist also embeds a ProductProfileResponse, and which
chat.py needs to import for its own compliance_checklist field). Both
modules import this one; neither imports the other.
"""

from pydantic import BaseModel


class ProductProfileResponse(BaseModel):
    product_name: str | None = None
    product_category: str | None = None
    product_type: str | None = None
    intended_use: str | None = None
    target_market: str | None = None
    manufacturing_location: str | None = None
    electrical_characteristics: str | None = None
    capacity: str | None = None
    materials: str | None = None
    technology: str | None = None
    application: str | None = None
    other_attributes: str | None = None

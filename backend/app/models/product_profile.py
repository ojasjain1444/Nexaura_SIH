"""
ProductProfile — Phase 10: the structured representation of the product a
user is asking about, built up progressively across a conversation's turns.

One row per Conversation (1:1) — a product-discovery conversation and its
evolving profile share the same lifecycle (deleting the conversation
deletes its profile; there is no reuse of one profile across conversations
in this phase).

Deliberately a fixed set of typed, nullable columns rather than a JSON
blob: this project already avoids JSON columns in favor of structured
tables (see app/models/certification_scheme.py's rationale), and a fixed
column set makes it structurally impossible to ever store an attribute
outside this schema — the extraction layer (app/product/profile_extraction.py)
can only ever set one of these named fields, never an arbitrary key. Every
field is independently nullable: discovery is progressive, and an unknown
attribute is represented honestly as NULL, never guessed or defaulted.

Kept intentionally small — the minimum fields needed to (a) classify a
product into a category for clarification-question selection and (b)
derive keyword search terms for retrieval. Not an attempt to model every
conceivable product attribute; `other_attributes` is a single free-text
overflow field for anything notable that doesn't fit a named column,
not a general-purpose extension point.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductProfile(Base):
    __tablename__ = "product_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Broad classification used to select which clarification-question set
    # applies (see app/product/clarification.py) — e.g. "water_heater",
    # "water_purifier". Free text, not a fixed enum: new categories are
    # added by adding a clarification-question entry, not a migration.
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # A finer distinction within the category, e.g. "storage" vs "instant"
    # for a water heater.
    product_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intended_use: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "domestic", "commercial"
    target_market: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "India"
    manufacturing_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Free text on purpose: voltage/wattage/current show up in wildly
    # different combinations and units across product categories — a single
    # descriptive field (e.g. "230V, 2000W") is honest about what was
    # actually stated, rather than forcing premature unit-specific columns.
    electrical_characteristics: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "15 litres"
    materials: Mapped[str | None] = mapped_column(String(500), nullable=True)  # e.g. materials in contact with water
    technology: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "RO", "UV", "immersion rod"
    application: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. specific use-case detail
    other_attributes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="product_profile")

    # The fixed, named fields an extractor is ever allowed to set — used by
    # app/product/profile_extraction.py to reject any unrecognized field
    # name from LLM output rather than silently storing it.
    EXTRACTABLE_FIELDS = (
        "product_name",
        "product_category",
        "product_type",
        "intended_use",
        "target_market",
        "manufacturing_location",
        "electrical_characteristics",
        "capacity",
        "materials",
        "technology",
        "application",
        "other_attributes",
    )

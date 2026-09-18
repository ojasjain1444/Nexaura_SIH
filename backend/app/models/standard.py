"""
Standard — persistent Indian Standard record, matching the frontend's
IndianStandard type (src/types/standards.ts) field-for-field:
  id, code, title, category, description, status, lastAmended, sector,
  relatedCodes[]

`related_codes` is a separate child table rather than a Postgres array
column, specifically so this schema works identically on SQLite (this
phase's default) and PostgreSQL (the documented future target) without
using a Postgres-only type.

`source_type` distinguishes seeded prototype/demo data from any future
verified BIS import — required per this phase's explicit instruction not
to silently present mock data as official BIS information.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Standard(Base):
    __tablename__ = "standards"
    __table_args__ = (
        # A standard code (e.g. "IS 14625") must be unique — two rows for
        # the same code would make "find the standard for X" ambiguous.
        UniqueConstraint("code", name="uq_standards_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Indexed + unique: the primary lookup key users and the frontend search
    # by (e.g. "IS 14625"); also enforces one row per real-world standard.
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Indexed: StandardsExplorerPage filters/searches by title substring.
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_amended: Mapped[date] = mapped_column(Date, nullable=False)
    sector: Mapped[str] = mapped_column(String(120), nullable=False)

    # "demo" for seeded prototype data (all current data is "demo" — see
    # docs/DATABASE.md). "verified_bis" is reserved for a future real import
    # and must never be set by the demo seed script.
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="demo")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    related_codes: Mapped[list["StandardRelatedCode"]] = relationship(
        "StandardRelatedCode", back_populates="standard", cascade="all, delete-orphan"
    )


class StandardRelatedCode(Base):
    """One related-standard code string per row (e.g. 'IS 302-2').
    Deliberately not a foreign key to another Standard row: the mock data
    references codes like 'IEC 60335-1' that are not themselves in the
    Standard table, so this must remain a plain string, matching the
    frontend's `relatedCodes: string[]` exactly."""

    __tablename__ = "standard_related_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    standard_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("standards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    standard: Mapped["Standard"] = relationship("Standard", back_populates="related_codes")

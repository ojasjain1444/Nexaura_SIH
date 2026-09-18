"""
CertificationScheme — matches the frontend's CertificationScheme type
(src/types/standards.ts):
  id, name, type, summary, eligibility[], steps[], averageDurationDays, fees

`steps` and `eligibility` are child tables rather than JSON columns:
- steps have an inherent order (order, title, description) that the
  frontend renders as a numbered list — a child table with an `order`
  column keeps that queryable/sortable at the database level rather than
  relying on array/JSON ordering semantics that differ between SQLite and
  PostgreSQL.
- eligibility is a plain list of requirement strings; modeled the same way
  as steps for consistency, since both are "ordered list of strings/structs
  belonging to one scheme."
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CertificationScheme(Base):
    __tablename__ = "certification_schemes"
    __table_args__ = (UniqueConstraint("name", name="uq_certification_schemes_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Indexed + unique: schemes are looked up and displayed by name; two
    # schemes with the same name would be indistinguishable in the UI.
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    average_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    fees: Mapped[str] = mapped_column(Text, nullable=False)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="demo")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    steps: Mapped[list["CertificationStep"]] = relationship(
        "CertificationStep", back_populates="scheme", cascade="all, delete-orphan", order_by="CertificationStep.order"
    )
    eligibility_items: Mapped[list["SchemeEligibility"]] = relationship(
        "SchemeEligibility", back_populates="scheme", cascade="all, delete-orphan", order_by="SchemeEligibility.order"
    )


class CertificationStep(Base):
    __tablename__ = "certification_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scheme_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("certification_schemes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    scheme: Mapped["CertificationScheme"] = relationship("CertificationScheme", back_populates="steps")


class SchemeEligibility(Base):
    __tablename__ = "scheme_eligibility_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scheme_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("certification_schemes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)

    scheme: Mapped["CertificationScheme"] = relationship("CertificationScheme", back_populates="eligibility_items")

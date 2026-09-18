"""
Lab — matches the frontend's TestingLab type (src/types/standards.ts):
  id, name, city, state, accreditations[], testCategories[], contact,
  distanceKm?

`accreditations` and `testCategories` are child tables for the same reason
as Standard.related_codes: portable across SQLite and PostgreSQL without
relying on array columns.

`distanceKm` is intentionally NOT persisted: in the current frontend it is
a client-side, request-relative value (distance from an implied user
location) — there is no fixed "distance" fact about a lab to store. If a
future phase computes this from real geocoding, it belongs in the API
response layer, not as a stored column on Lab.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Indexed: LabDirectoryPage searches by name substring.
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Indexed: search also matches by city.
    city: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    contact: Mapped[str] = mapped_column(String(255), nullable=False)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="demo")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    accreditations: Mapped[list["LabAccreditation"]] = relationship(
        "LabAccreditation", back_populates="lab", cascade="all, delete-orphan"
    )
    test_categories: Mapped[list["LabTestCategory"]] = relationship(
        "LabTestCategory", back_populates="lab", cascade="all, delete-orphan"
    )


class LabAccreditation(Base):
    __tablename__ = "lab_accreditations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True)
    accreditation: Mapped[str] = mapped_column(String(50), nullable=False)

    lab: Mapped["Lab"] = relationship("Lab", back_populates="accreditations")


class LabTestCategory(Base):
    __tablename__ = "lab_test_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    lab: Mapped["Lab"] = relationship("Lab", back_populates="test_categories")

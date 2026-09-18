"""
SQLAlchemy declarative base.

Phase 1 scope: this module defines the base class that future models
(Phase 2 onward) will inherit from. No tables are defined here, and no
tables are created by Phase 1 — there is nothing to persist yet.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

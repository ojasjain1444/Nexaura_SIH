"""storage — Persistence layer for the BIS ingestion pipeline."""

from .db import BISDatabase

__all__ = ["BISDatabase"]

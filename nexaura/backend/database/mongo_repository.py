"""
mongo_repository.py — MongoDB Repository Implementation for Nexaura KnowledgeBase

Project: Nexaura (SIH 2026 — SIH26107)

Provides MongoDB CRUD operations for:
    - Documents / Standards (metadata)
    - Clauses (KnowledgeUnits)
    - Tables
    - Technical Features
    - Evidence Relationships
    - Sources & Provenance
    - Processing Log (Resume support)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MongoRepository:
    """
    CRUD repository for the Nexaura KnowledgeBase stored in MongoDB.
    """

    def __init__(self, mongo_manager) -> None:
        self.mongo = mongo_manager
        self.db = self.mongo.get_db()

    # =========================================================================
    # Standards / Documents Metadata
    # =========================================================================

    def upsert_standard(
        self, standard_number: str, title: Optional[str], status: str, source_pdf: str
    ) -> str:
        """Insert or update a document/standard record."""
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "standard_number": standard_number,
            "title": title,
            "status": status,
            "source_pdf": source_pdf,
            "updated_at": now,
        }
        self.db.documents.update_one(
            {"standard_number": standard_number},
            {"$set": doc},
            upsert=True,
        )
        return standard_number

    def get_standard_id(self, standard_number: str) -> Optional[str]:
        """Get standard identifier."""
        doc = self.db.documents.find_one({"standard_number": standard_number}, {"_id": 1, "standard_number": 1})
        return doc["standard_number"] if doc else None

    # =========================================================================
    # Editions
    # =========================================================================

    def upsert_edition(
        self,
        standard_number: str,
        edition: Optional[str],
        year: Optional[int],
        scope: Optional[str],
        foreword: Optional[str],
    ) -> str:
        """Update edition details in the document metadata."""
        edition_data = {
            "edition": edition,
            "year": year,
            "scope": scope,
            "foreword": foreword,
        }
        self.db.documents.update_one(
            {"standard_number": standard_number},
            {"$set": edition_data},
            upsert=True,
        )
        return standard_number

    # =========================================================================
    # Clauses (KnowledgeUnits)
    # =========================================================================

    def upsert_clause(self, ku, standard_identifier: str, edition_identifier: Optional[str] = None) -> str:
        """Insert or update a single KnowledgeUnit as a clause document in MongoDB."""
        now = datetime.now(timezone.utc).isoformat()

        doc = {
            "knowledge_unit_id": ku.id,
            "standard_number": ku.standard_number,
            "clause": ku.clause,
            "sub_clause": ku.sub_clause,
            "parent_clause": ku.parent_clause,
            "section": ku.section,
            "heading": ku.heading,
            "content_type": ku.content_type,
            "annex": ku.annex,
            "depth": getattr(ku, "depth", 0),
            "raw_text": ku.raw_text,
            "clean_text": ku.clean_text,
            "summary": ku.summary,
            "keywords": ku.keywords,
            "entities": ku.entities,
            "product": ku.product,
            "application": ku.application,
            "material": ku.material,
            "process": ku.process,
            "industry": ku.industry,
            "domain": ku.domain,
            "technical_parameters": [p.model_dump() for p in ku.technical_parameters],
            "requirements": [r.model_dump() for r in ku.requirements],
            "cross_references": ku.cross_references,
            "page_start": ku.page_start,
            "page_end": ku.page_end,
            "source_pdf": ku.source_pdf,
            "extraction_method": ku.extraction_method,
            "ocr_confidence": ku.ocr_confidence,
            "needs_review": ku.needs_review,
            "validation_status": ku.validation_status,
            "review_reason": ku.review_reason,
            "search_text": ku.search_text,
            "updated_at": now,
        }

        self.db.clauses.update_one(
            {"knowledge_unit_id": ku.id},
            {"$set": doc},
            upsert=True,
        )
        return ku.id

    def batch_insert_clauses(
        self,
        knowledge_units: list,
        standard_identifier: str,
        edition_identifier: Optional[str] = None,
        batch_size: int = 50,
    ) -> int:
        """Batch insert KnowledgeUnits into MongoDB."""
        inserted = 0
        for i in range(0, len(knowledge_units), batch_size):
            batch = knowledge_units[i : i + batch_size]
            for ku in batch:
                try:
                    self.upsert_clause(ku, standard_identifier, edition_identifier)
                    inserted += 1
                except Exception as exc:
                    logger.error("Failed to insert clause %s: %s", getattr(ku, "id", "unknown"), exc)
        return inserted

    # =========================================================================
    # Tables
    # =========================================================================

    def upsert_table(self, table_record, standard_identifier: str) -> None:
        """Insert or update a table document in MongoDB."""
        doc = {
            "table_id": table_record.table_id,
            "standard_number": table_record.standard_number,
            "source_table_ref": table_record.source_table_ref,
            "clause": table_record.clause,
            "page": table_record.page,
            "caption": table_record.caption,
            "columns": table_record.columns,
            "rows": table_record.rows,
            "units": table_record.units,
            "footnotes": table_record.footnotes,
            "search_text": table_record.search_text,
            "source_pdf": table_record.source_pdf,
            "needs_review": table_record.needs_review,
        }
        self.db.tables.update_one(
            {"table_id": table_record.table_id},
            {"$set": doc},
            upsert=True,
        )

    # =========================================================================
    # Features
    # =========================================================================

    def insert_features(self, knowledge_units: list, standard_number: str) -> int:
        """Insert technical feature parameters into MongoDB features collection."""
        count = 0
        for ku in knowledge_units:
            for idx, param in enumerate(ku.technical_parameters, start=1):
                try:
                    feat_id = f"{ku.id}_feat_{idx}"
                    feat_doc = {
                        "feature_id": feat_id,
                        "knowledge_unit_id": ku.id,
                        "standard_number": standard_number,
                        "clause": ku.clause,
                        "parameter_name": param.name,
                        "value": param.value,
                        "value_str": param.value_str,
                        "unit": param.unit,
                        "operator": param.operator,
                        "range_min": param.range_min,
                        "range_max": param.range_max,
                        "material": param.material,
                        "context": param.context,
                    }
                    self.db.features.update_one(
                        {"feature_id": feat_id},
                        {"$set": feat_doc},
                        upsert=True,
                    )
                    count += 1
                except Exception as exc:
                    logger.warning("Feature insert failed: %s", exc)
        return count

    # =========================================================================
    # Relationships
    # =========================================================================

    def insert_relationships(self, standard_identifier: str, metadata) -> None:
        """Insert evidence-based relationships for a standard."""
        rels = []
        if metadata.supersedes:
            rels.append({"from_standard_number": metadata.standard_number, "to_standard_ref": metadata.supersedes, "relation_type": "supersedes", "source_evidence": "document_metadata"})
        if metadata.superseded_by:
            rels.append({"from_standard_number": metadata.standard_number, "to_standard_ref": metadata.superseded_by, "relation_type": "superseded_by", "source_evidence": "document_metadata"})
        for ref in metadata.references:
            rels.append({"from_standard_number": metadata.standard_number, "to_standard_ref": ref, "relation_type": "references", "source_evidence": "document_references"})
        for amend in metadata.amended_by:
            rels.append({"from_standard_number": metadata.standard_number, "to_standard_ref": amend, "relation_type": "amended_by", "source_evidence": "document_metadata"})

        for rel in rels:
            self.db.relationships.update_one(
                {
                    "from_standard_number": rel["from_standard_number"],
                    "to_standard_ref": rel["to_standard_ref"],
                    "relation_type": rel["relation_type"],
                },
                {"$set": rel},
                upsert=True,
            )

    # =========================================================================
    # Sources
    # =========================================================================

    def upsert_source(
        self,
        standard_identifier: str,
        source_pdf: str,
        file_hash: str,
        file_size: int,
        total_pages: int,
        processed_pages: int,
        gemini_pages: int,
        text_pages: int,
    ) -> None:
        """Record PDF source provenance in MongoDB."""
        doc = {
            "standard_number": standard_identifier,
            "source_pdf": source_pdf,
            "file_hash": file_hash,
            "file_size_bytes": file_size,
            "total_pages": total_pages,
            "processed_pages": processed_pages,
            "gemini_pages": gemini_pages,
            "text_pages": text_pages,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.sources.update_one(
            {"source_pdf": source_pdf, "file_hash": file_hash},
            {"$set": doc},
            upsert=True,
        )

    # =========================================================================
    # Processing Log (Resume Support)
    # =========================================================================

    def log_processing_start(self, source_pdf: str, file_hash: str) -> None:
        """Mark a PDF as processing in MongoDB."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.processing_log.update_one(
            {"file_hash": file_hash},
            {
                "$set": {
                    "source_pdf": source_pdf,
                    "file_hash": file_hash,
                    "status": "processing",
                    "started_at": now,
                }
            },
            upsert=True,
        )

    def log_processing_complete(
        self,
        file_hash: str,
        clauses: int,
        tables: int,
        features: int,
        avg_confidence: float,
    ) -> None:
        """Mark a PDF as completed in MongoDB."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.processing_log.update_one(
            {"file_hash": file_hash},
            {
                "$set": {
                    "status": "completed",
                    "clauses_extracted": clauses,
                    "tables_extracted": tables,
                    "features_extracted": features,
                    "avg_confidence": avg_confidence,
                    "completed_at": now,
                }
            },
        )

    def log_processing_failed(self, file_hash: str, error: str) -> None:
        """Mark a PDF as failed in MongoDB."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.processing_log.update_one(
            {"file_hash": file_hash},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error[:2000],
                    "completed_at": now,
                }
            },
        )

    def is_already_processed(self, file_hash: str) -> bool:
        """Check if PDF hash is already processed in MongoDB."""
        doc = self.db.processing_log.find_one({"file_hash": file_hash}, {"status": 1})
        return doc is not None and doc.get("status") == "completed"

    # =========================================================================
    # Query Helpers
    # =========================================================================

    def get_all_clause_search_texts(self) -> list[dict]:
        """Retrieve all clauses with their search text for BM25 indexing."""
        cursor = self.db.clauses.find(
            {"search_text": {"$ne": None, "$nin": [""]}},
            {"knowledge_unit_id": 1, "search_text": 1, "standard_number": 1},
        )
        return [
            {
                "id": doc.get("knowledge_unit_id"),
                "search_text": doc.get("search_text", ""),
                "standard_number": doc.get("standard_number", ""),
            }
            for doc in cursor
        ]

    def get_clause_by_id(self, knowledge_unit_id: str) -> Optional[dict]:
        """Retrieve a clause by its KnowledgeUnit ID from MongoDB."""
        doc = self.db.clauses.find_one({"knowledge_unit_id": knowledge_unit_id})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    # =========================================================================
    # Acquisition & Document Inventory Persistence
    # =========================================================================

    def save_inventory_and_coverage(self, inventory_payload: dict, coverage_payload: dict) -> None:
        """Persist documents_inventory and coverage_reports into MongoDB."""
        try:
            # 1. Save documents inventory
            docs = inventory_payload.get("documents", [])
            for d in docs:
                self.db.documents_inventory.update_one(
                    {"document_id": d["document_id"]},
                    {"$set": d},
                    upsert=True,
                )

            # 2. Save document relationships
            rels = inventory_payload.get("relationships", [])
            for r in rels:
                self.db.document_relationships.update_one(
                    {"from_id": r["from_id"], "to_id": r["to_id"], "relation_type": r["relation_type"]},
                    {"$set": r},
                    upsert=True,
                )

            # 3. Save coverage reports
            coverage = coverage_payload.get("coverage", [])
            for c in coverage:
                self.db.coverage_reports.update_one(
                    {"standard_number": c["standard_number"]},
                    {"$set": c},
                    upsert=True,
                )

            logger.info(
                "Persisted %d documents and %d coverage reports to MongoDB 'KnowledgeBase'",
                len(docs), len(coverage),
            )
        except Exception as exc:
            logger.error("Failed to persist document inventory to MongoDB: %s", exc)


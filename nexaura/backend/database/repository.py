"""
repository.py — Database CRUD Operations

Project: Nexaura (SIH 2026 — SIH26107)

Batch-optimized CRUD for:
    - Standards
    - Editions
    - Clauses (KnowledgeUnits)
    - Tables
    - Features
    - Relationships
    - Processing Log (for resume support)

Design principles:
    - Batch inserts (configurable batch_size)
    - Upsert (INSERT ... ON CONFLICT DO UPDATE)
    - Never lose data — partial batches still committed
    - Processing log enables exact resume after failure
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BISRepository:
    """
    CRUD repository for the Nexaura BIS knowledge base.

    All operations use psycopg2 connections from PostgreSQLManager.
    """

    def __init__(self, pg_manager) -> None:
        self.pg = pg_manager

    # =========================================================================
    # Standards
    # =========================================================================

    def upsert_standard(self, standard_number: str, title: Optional[str], status: str, source_pdf: str) -> int:
        """Insert or update a standard record. Returns standard.id."""
        sql = """
            INSERT INTO standards (standard_number, title, status, source_pdf, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (standard_number)
            DO UPDATE SET
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                source_pdf = EXCLUDED.source_pdf,
                updated_at = NOW()
            RETURNING id
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (standard_number, title, status, source_pdf))
                row = cur.fetchone()
                conn.commit()
                return row[0]

    def get_standard_id(self, standard_number: str) -> Optional[int]:
        """Get the internal ID for a standard number."""
        sql = "SELECT id FROM standards WHERE standard_number = %s"
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (standard_number,))
                row = cur.fetchone()
                return row[0] if row else None

    # =========================================================================
    # Editions
    # =========================================================================

    def upsert_edition(
        self,
        standard_id: int,
        edition: Optional[str],
        year: Optional[int],
        scope: Optional[str],
        foreword: Optional[str],
    ) -> int:
        """Insert or update an edition record. Returns edition.id."""
        sql = """
            INSERT INTO editions (standard_id, edition, year, scope, foreword)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (standard_id, edition, year)
            DO UPDATE SET scope = EXCLUDED.scope, foreword = EXCLUDED.foreword
            RETURNING id
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (standard_id, edition, year, scope, foreword))
                row = cur.fetchone()
                conn.commit()
                return row[0]

    # =========================================================================
    # Clauses (KnowledgeUnits)
    # =========================================================================

    def upsert_clause(self, ku, standard_id: int, edition_id: Optional[int]) -> int:
        """Insert or update a single KnowledgeUnit as a clause record."""
        sql = """
            INSERT INTO clauses (
                standard_id, edition_id, knowledge_unit_id,
                clause, sub_clause, parent_clause, section, heading,
                content_type, annex, depth,
                raw_text, clean_text, summary,
                keywords, entities, product, application, material, process, industry, domain,
                technical_parameters, requirements, cross_references,
                page_start, page_end, source_pdf,
                extraction_method, ocr_confidence,
                needs_review, validation_status, review_reason,
                search_text, updated_at
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, NOW()
            )
            ON CONFLICT (knowledge_unit_id)
            DO UPDATE SET
                clean_text          = EXCLUDED.clean_text,
                summary             = EXCLUDED.summary,
                keywords            = EXCLUDED.keywords,
                product             = EXCLUDED.product,
                application         = EXCLUDED.application,
                material            = EXCLUDED.material,
                technical_parameters= EXCLUDED.technical_parameters,
                requirements        = EXCLUDED.requirements,
                search_text         = EXCLUDED.search_text,
                ocr_confidence      = EXCLUDED.ocr_confidence,
                needs_review        = EXCLUDED.needs_review,
                validation_status   = EXCLUDED.validation_status,
                updated_at          = NOW()
            RETURNING id
        """
        params = (
            standard_id, edition_id, ku.id,
            ku.clause, ku.sub_clause, ku.parent_clause, ku.section, ku.heading,
            ku.content_type, ku.annex, getattr(ku, "depth", 0),
            ku.raw_text, ku.clean_text, ku.summary,
            json.dumps(ku.keywords), json.dumps(ku.entities),
            json.dumps(ku.product), json.dumps(ku.application),
            json.dumps(ku.material), json.dumps(ku.process),
            json.dumps(ku.industry), json.dumps(ku.domain),
            json.dumps([p.model_dump() for p in ku.technical_parameters]),
            json.dumps([r.model_dump() for r in ku.requirements]),
            json.dumps(ku.cross_references),
            ku.page_start, ku.page_end, ku.source_pdf,
            ku.extraction_method, ku.ocr_confidence,
            ku.needs_review, ku.validation_status, ku.review_reason,
            ku.search_text,
        )
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                conn.commit()
                return row[0]

    def batch_insert_clauses(
        self,
        knowledge_units: list,
        standard_id: int,
        edition_id: Optional[int],
        batch_size: int = 50,
    ) -> int:
        """Batch insert KnowledgeUnits. Returns count of inserted/updated records."""
        inserted = 0
        for i in range(0, len(knowledge_units), batch_size):
            batch = knowledge_units[i:i + batch_size]
            for ku in batch:
                try:
                    self.upsert_clause(ku, standard_id, edition_id)
                    inserted += 1
                except Exception as exc:
                    logger.error("Failed to insert clause %s: %s", ku.id, exc)
            logger.debug("Inserted batch %d/%d (%d records)", i // batch_size + 1,
                         (len(knowledge_units) + batch_size - 1) // batch_size, len(batch))
        return inserted

    # =========================================================================
    # Tables
    # =========================================================================

    def upsert_table(self, table_record, standard_id: int) -> None:
        """Insert or update a table record."""
        sql = """
            INSERT INTO document_tables (
                table_id, standard_id, source_table_ref, clause, page,
                caption, columns, rows, units, footnotes,
                search_text, source_pdf, standard_number, needs_review
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_id)
            DO UPDATE SET
                search_text     = EXCLUDED.search_text,
                needs_review    = EXCLUDED.needs_review
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    table_record.table_id,
                    standard_id,
                    table_record.source_table_ref,
                    table_record.clause,
                    table_record.page,
                    table_record.caption,
                    json.dumps(table_record.columns),
                    json.dumps(table_record.rows),
                    json.dumps(table_record.units),
                    json.dumps(table_record.footnotes),
                    table_record.search_text,
                    table_record.source_pdf,
                    table_record.standard_number,
                    table_record.needs_review,
                ))
                conn.commit()

    # =========================================================================
    # Features
    # =========================================================================

    def insert_features(self, knowledge_units: list, standard_number: str) -> int:
        """Extract and insert individual TechnicalParameter records."""
        sql = """
            INSERT INTO features (
                knowledge_unit_id, standard_number,
                parameter_name, value, value_str, unit, operator,
                range_min, range_max, material, context
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        count = 0
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                for ku in knowledge_units:
                    for param in ku.technical_parameters:
                        try:
                            cur.execute(sql, (
                                ku.id, standard_number,
                                param.name, param.value, param.value_str,
                                param.unit, param.operator,
                                param.range_min, param.range_max,
                                param.material, param.context,
                            ))
                            count += 1
                        except Exception as exc:
                            logger.warning("Feature insert failed: %s", exc)
            conn.commit()
        return count

    # =========================================================================
    # Relationships
    # =========================================================================

    def insert_relationships(self, standard_id: int, metadata) -> None:
        """Insert all evidence-based relationships for a standard."""
        sql = """
            INSERT INTO relationships (from_standard_id, to_standard_ref, relation_type, source_evidence)
            VALUES (%s, %s, %s, %s)
        """
        rels = []
        if metadata.supersedes:
            rels.append((standard_id, metadata.supersedes, "supersedes", "document_metadata"))
        if metadata.superseded_by:
            rels.append((standard_id, metadata.superseded_by, "superseded_by", "document_metadata"))
        for ref in metadata.references:
            rels.append((standard_id, ref, "references", "document_references"))
        for amend in metadata.amended_by:
            rels.append((standard_id, amend, "amended_by", "document_metadata"))

        if not rels:
            return

        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rels)
            conn.commit()

    # =========================================================================
    # Sources
    # =========================================================================

    def upsert_source(
        self,
        standard_id: int,
        source_pdf: str,
        file_hash: str,
        file_size: int,
        total_pages: int,
        processed_pages: int,
        gemini_pages: int,
        text_pages: int,
    ) -> None:
        """Record PDF source provenance."""
        sql = """
            INSERT INTO sources (
                standard_id, source_pdf, file_hash, file_size_bytes,
                total_pages, processed_pages, gemini_pages, text_pages
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_pdf, file_hash) DO NOTHING
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    standard_id, source_pdf, file_hash, file_size,
                    total_pages, processed_pages, gemini_pages, text_pages,
                ))
            conn.commit()

    # =========================================================================
    # Processing Log (Resume Support)
    # =========================================================================

    def log_processing_start(self, source_pdf: str, file_hash: str) -> None:
        """Mark a PDF as currently being processed."""
        sql = """
            INSERT INTO processing_log (source_pdf, file_hash, status, started_at)
            VALUES (%s, %s, 'processing', NOW())
            ON CONFLICT (file_hash) DO UPDATE SET status = 'processing', started_at = NOW()
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source_pdf, file_hash))
            conn.commit()

    def log_processing_complete(
        self,
        file_hash: str,
        clauses: int,
        tables: int,
        features: int,
        avg_confidence: float,
    ) -> None:
        """Mark a PDF as successfully processed."""
        sql = """
            UPDATE processing_log
            SET status = 'completed',
                clauses_extracted = %s,
                tables_extracted = %s,
                features_extracted = %s,
                avg_confidence = %s,
                completed_at = NOW()
            WHERE file_hash = %s
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (clauses, tables, features, avg_confidence, file_hash))
            conn.commit()

    def log_processing_failed(self, file_hash: str, error: str) -> None:
        """Mark a PDF as failed."""
        sql = """
            UPDATE processing_log
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE file_hash = %s
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (error[:2000], file_hash))
            conn.commit()

    def is_already_processed(self, file_hash: str) -> bool:
        """Check if a PDF (by hash) was already successfully processed."""
        sql = "SELECT status FROM processing_log WHERE file_hash = %s"
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (file_hash,))
                row = cur.fetchone()
                return row is not None and row[0] == "completed"

    # =========================================================================
    # Query helpers
    # =========================================================================

    def get_all_clause_search_texts(self) -> list[dict]:
        """Retrieve all clauses with their search text for BM25 indexing."""
        sql = """
            SELECT knowledge_unit_id, search_text, standard_number_ref.standard_number
            FROM clauses c
            JOIN standards s ON c.standard_id = s.id
            WHERE c.search_text IS NOT NULL AND c.search_text != ''
            ORDER BY c.id
        """
        # Simplified version without JOIN alias issue
        sql = """
            SELECT c.knowledge_unit_id, c.search_text, s.standard_number
            FROM clauses c
            JOIN standards s ON c.standard_id = s.id
            WHERE c.search_text IS NOT NULL AND c.search_text != ''
            ORDER BY c.id
        """
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [
                    {"id": row[0], "search_text": row[1], "standard_number": row[2]}
                    for row in cur.fetchall()
                ]

    def get_clause_by_id(self, knowledge_unit_id: str) -> Optional[dict]:
        """Retrieve a clause by its KnowledgeUnit ID."""
        sql = "SELECT * FROM clauses WHERE knowledge_unit_id = %s"
        with self.pg.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (knowledge_unit_id,))
                row = cur.fetchone()
                if row:
                    cols = [desc[0] for desc in cur.description]
                    return dict(zip(cols, row))
        return None

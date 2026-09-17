"""
pipeline.py — End-to-End Ingestion Orchestration

Project: Nexaura (SIH 2026 — SIH26107)

Orchestrates the complete BIS PDF ingestion pipeline:

    For each PDF in data/raw/:
        1. Check file_hash → skip if already completed (resume)
        2. pdf_detector → classify pages
        3. text_extractor → direct text for text pages
        4. gemini_ocr → Gemini Flash for scanned/image pages
        5. layout_parser + clause_parser → ClauseTree
        6. table_parser → TableRecords
        7. metadata_extractor → document metadata
        8. feature_extractor → KnowledgeUnits
        9. cleaner → clean_text
        10. validator → flag/validate
        11. graph_builder → update knowledge graph
        12. repository → PostgreSQL insert
        13. embedding_service → generate vectors
        14. qdrant → vector upsert
        15. bm25 → update index
        16. write JSONL output files
        17. mark_processed()
        18. processing_report → update

Features:
    - Resume: skip already-processed PDFs
    - Parallel workers: configurable
    - Incremental ingestion
    - Failure recovery: one failed PDF does not stop the batch
    - Per-PDF processing log
    - Full processing report generation
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Processing Report
# =============================================================================

@dataclass
class ProcessingReport:
    """Aggregate report for a pipeline run."""

    # Counts
    total_pdfs: int = 0
    processed_pdfs: int = 0
    failed_pdfs: int = 0
    skipped_pdfs: int = 0      # Already processed (resume)

    # PDF types
    text_pdfs: int = 0
    scanned_pdfs: int = 0
    mixed_pdfs: int = 0

    # Page counts
    total_pages: int = 0
    processed_pages: int = 0
    gemini_pages: int = 0
    text_pages_direct: int = 0

    # Extraction counts
    total_clauses: int = 0
    total_tables: int = 0
    total_features: int = 0
    total_embeddings: int = 0

    # Quality
    average_confidence: float = 0.0
    low_confidence_pages: int = 0
    flagged_records: int = 0
    duplicate_files: int = 0

    # Errors
    api_errors: int = 0
    retry_count: int = 0

    # Timing
    processing_time_seconds: float = 0.0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None

    # Per-PDF results
    pdf_results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_pdfs":             self.total_pdfs,
            "processed_pdfs":         self.processed_pdfs,
            "failed_pdfs":            self.failed_pdfs,
            "skipped_pdfs":           self.skipped_pdfs,
            "text_pdfs":              self.text_pdfs,
            "scanned_pdfs":           self.scanned_pdfs,
            "mixed_pdfs":             self.mixed_pdfs,
            "total_pages":            self.total_pages,
            "processed_pages":        self.processed_pages,
            "gemini_pages":           self.gemini_pages,
            "text_pages_direct":      self.text_pages_direct,
            "total_clauses":          self.total_clauses,
            "total_tables":           self.total_tables,
            "total_features":         self.total_features,
            "total_embeddings":       self.total_embeddings,
            "average_confidence":     round(self.average_confidence, 4),
            "low_confidence_pages":   self.low_confidence_pages,
            "flagged_records":        self.flagged_records,
            "duplicate_files":        self.duplicate_files,
            "api_errors":             self.api_errors,
            "retry_count":            self.retry_count,
            "processing_time_seconds":round(self.processing_time_seconds, 2),
            "started_at":             self.started_at,
            "finished_at":            self.finished_at,
            "errors":                 self.errors,
        }


# =============================================================================
# Pipeline Configuration
# =============================================================================

@dataclass
class PipelineConfig:
    """Configuration for a pipeline run."""
    input_dir: Path
    output_dir: Path
    workers: int = 1
    resume: bool = True
    force: bool = False                  # Reprocess even if cached
    skip_ocr: bool = False               # Use only text extraction
    skip_embeddings: bool = False        # Skip Qdrant/BM25
    specific_pdf: Optional[Path] = None  # Process only one PDF

    # Gemini settings
    gemini_api_key: Optional[str] = None
    gemini_model: Optional[str] = None

    # Embedding settings
    embedding_provider: str = "sentence_transformers"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Search settings
    top_k: int = 10
    similarity_weights: Optional[dict] = None

    # DB settings
    mongo_url: Optional[str] = None
    mongo_db_name: str = "KnowledgeBase"
    postgres_url: Optional[str] = None
    qdrant_url: Optional[str] = None

    # Paths
    bm25_index_path: Optional[Path] = None
    knowledge_graph_path: Optional[Path] = None
    processing_report_path: Optional[Path] = None
    failed_log_path: Optional[Path] = None
    low_confidence_log_path: Optional[Path] = None
    cache_dir: Optional[Path] = None


# =============================================================================
# Single PDF Processor
# =============================================================================

class PDFProcessor:
    """
    Processes a single BIS PDF through the complete ingestion pipeline.

    Used by NexauraPipeline for both single and batch processing.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._init_modules()

    def _init_modules(self) -> None:
        """Lazy-initialize all pipeline modules."""
        from nexaura.backend.ingestion.pdf_detector import PDFDetector
        from nexaura.backend.ingestion.text_extractor import TextExtractor
        from nexaura.backend.ingestion.gemini_ocr import GeminiOCR
        from nexaura.backend.ingestion.layout_parser import LayoutParser
        from nexaura.backend.ingestion.clause_parser import ClauseParser
        from nexaura.backend.ingestion.table_parser import TableParser
        from nexaura.backend.ingestion.metadata_extractor import MetadataExtractor
        from nexaura.backend.ingestion.feature_extractor import FeatureExtractor
        from nexaura.backend.ingestion.cleaner import DataCleaner
        from nexaura.backend.ingestion.validator import KnowledgeUnitValidator

        self.pdf_detector    = PDFDetector()
        self.text_extractor  = TextExtractor()
        self.layout_parser   = LayoutParser()
        self.clause_parser   = ClauseParser()
        self.table_parser    = TableParser()
        self.metadata_extractor = MetadataExtractor()
        self.feature_extractor  = FeatureExtractor()
        self.cleaner         = DataCleaner()
        self.validator       = KnowledgeUnitValidator(
            low_confidence_log=self.config.low_confidence_log_path
        )

        # Gemini OCR (initialized only if not skip_ocr)
        if not self.config.skip_ocr:
            self.gemini = GeminiOCR(
                api_key=self.config.gemini_api_key,
                model=self.config.gemini_model,
                cache_dir=self.config.cache_dir,
                failed_log_path=self.config.failed_log_path,
            )
        else:
            self.gemini = None

    def process(self, pdf_path: Path) -> dict[str, Any]:
        """
        Process a single PDF end-to-end.

        Args:
            pdf_path: Path to the BIS PDF.

        Returns:
            Result dict with extracted knowledge units, tables, metadata.
        """
        start = time.time()
        logger.info("=" * 60)
        logger.info("Processing: %s", pdf_path.name)

        result: dict[str, Any] = {
            "pdf_name": pdf_path.name,
            "success": False,
            "knowledge_units": [],
            "tables": [],
            "metadata": None,
            "file_hash": "",
            "pdf_type": "unknown",
            "total_pages": 0,
            "gemini_pages": 0,
            "text_pages": 0,
            "avg_confidence": 0.0,
            "clauses_extracted": 0,
            "tables_extracted": 0,
            "features_extracted": 0,
            "flagged_records": 0,
            "error": None,
        }

        try:
            # === Phase 1: PDF Analysis ===
            pdf_analysis = self.pdf_detector.analyse(pdf_path)
            result["file_hash"]   = pdf_analysis.file_hash
            result["pdf_type"]    = pdf_analysis.pdf_type.value
            result["total_pages"] = pdf_analysis.total_pages

            if not pdf_analysis.is_valid:
                raise ValueError(f"Invalid PDF: {pdf_analysis.error_message}")

            # === Phase 2: Document Processing ===
            gemini_data: dict = {}
            text_pages_processed = 0
            gemini_pages_processed = 0

            if self.config.skip_ocr or pdf_analysis.pdf_type.value == "text_pdf":
                # Text extraction only
                logger.info("Using text extraction for %s", pdf_path.name)
                text_result = self.text_extractor.extract_pdf(pdf_path)
                layout = self.layout_parser.parse_text_extraction(text_result, pdf_path.name)
                text_pages_processed = pdf_analysis.text_pages
                # Build minimal gemini_data for metadata/table extraction
                gemini_data = {"clauses": [], "tables": [], "needs_review": False, "standard_number": "unknown"}

            else:
                # Gemini Flash document intelligence
                logger.info("Using Gemini Flash for %s", pdf_path.name)
                ocr_result = self.gemini.process_pdf(pdf_path, file_hash=pdf_analysis.file_hash)
                gemini_data = ocr_result.data
                layout = self.layout_parser.parse_gemini_output(gemini_data, pdf_path.name)
                gemini_pages_processed = pdf_analysis.pages_requiring_gemini

            result["gemini_pages"] = gemini_pages_processed
            result["text_pages"]   = text_pages_processed

            # === Phase 3: Clause Hierarchy ===
            clause_nodes = self.clause_parser.parse(layout)

            # === Phase 4: Table Extraction ===
            tables = self.table_parser.parse(gemini_data, pdf_path.name)
            result["tables"] = tables
            result["tables_extracted"] = len(tables)

            # === Phase 5: Metadata ===
            self.validator.reset_document_state()
            meta = self.metadata_extractor.extract(gemini_data, pdf_path.name)
            result["metadata"] = meta

            # === Phase 6+7: Feature Extraction → KnowledgeUnits ===
            ocr_confidence = gemini_data.get("confidence", 0.95) if not self.config.skip_ocr else 0.90

            knowledge_units = []
            for node in clause_nodes:
                if not node.raw_text and not node.text:
                    continue
                ku = self.feature_extractor.extract(
                    clause_node=node,
                    document_meta=meta,
                    source_pdf=pdf_path.name,
                    ocr_confidence=ocr_confidence,
                )
                knowledge_units.append(ku)

            # === Phase 8: Cleaning ===
            for ku in knowledge_units:
                self.cleaner.clean_knowledge_unit(ku)

            # === Phase 9: Validation ===
            knowledge_units, val_report = self.validator.validate_batch(knowledge_units)
            result["flagged_records"] = val_report.flagged_units

            # === Compute stats ===
            total_features = sum(len(ku.technical_parameters) for ku in knowledge_units)
            confidences = [ku.ocr_confidence for ku in knowledge_units if ku.ocr_confidence > 0]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            result.update({
                "success": True,
                "knowledge_units": knowledge_units,
                "clauses_extracted": len(knowledge_units),
                "features_extracted": total_features,
                "avg_confidence": avg_conf,
            })

            elapsed = time.time() - start
            logger.info(
                "✓ %s complete in %.1fs | clauses=%d tables=%d features=%d flagged=%d",
                pdf_path.name, elapsed,
                len(knowledge_units), len(tables), total_features, val_report.flagged_units,
            )

        except Exception as exc:
            elapsed = time.time() - start
            logger.error("✗ %s FAILED in %.1fs: %s", pdf_path.name, elapsed, exc, exc_info=True)
            result["error"] = str(exc)

        return result


# =============================================================================
# Main Pipeline Orchestrator
# =============================================================================

class NexauraPipeline:
    """
    Main orchestrator for the Nexaura BIS Knowledge Base Builder.

    Processes PDFs from input_dir, stores results in databases,
    writes JSONL output files, and generates a processing report.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self._setup_directories()
        self._init_databases()
        self._init_search()
        self._graph_builder = None
        self.report = ProcessingReport()

    def _setup_directories(self) -> None:
        """Create all required output directories."""
        dirs = [
            self.config.output_dir,
            self.config.output_dir.parent / "logs",
            self.config.output_dir.parent / "embeddings",
            self.config.output_dir.parent / "checkpoints",
        ]
        if self.config.cache_dir:
            dirs.append(self.config.cache_dir)
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)

    def _init_databases(self) -> None:
        """Initialize database connections and schema."""
        self.mongo_manager = None
        self.qdrant_manager = None
        self.repository = None

        # MongoDB
        try:
            from nexaura.backend.database.mongo_manager import MongoDBManager
            from nexaura.backend.database.mongo_repository import MongoRepository
            self.mongo_manager = MongoDBManager(
                url=self.config.mongo_url,
                db_name=self.config.mongo_db_name,
            )
            self.mongo_manager.init_collections()
            self.repository = MongoRepository(self.mongo_manager)
            logger.info("MongoDB connected and database 'KnowledgeBase' initialized")
        except Exception as exc:
            logger.warning("MongoDB unavailable — running without DB: %s", exc)

        # Qdrant
        if not self.config.skip_embeddings:
            try:
                from nexaura.backend.database.qdrant import QdrantManager
                self.qdrant_manager = QdrantManager(url=self.config.qdrant_url)
                self.qdrant_manager.init_collection()
                logger.info("Qdrant connected and collection ready")
            except Exception as exc:
                logger.warning("Qdrant unavailable — running without vector DB: %s", exc)

    def _init_search(self) -> None:
        """Initialize embedding service and BM25 index."""
        self.embedding_service = None
        self.bm25_index = None

        if not self.config.skip_embeddings:
            try:
                from nexaura.backend.embeddings.embedding_service import create_embedding_service
                self.embedding_service = create_embedding_service(
                    provider=self.config.embedding_provider,
                    model=self.config.embedding_model,
                )
                logger.info("Embedding service ready: dim=%d", self.embedding_service.dimension)
            except Exception as exc:
                logger.warning("Embedding service unavailable: %s", exc)

            # Load existing BM25 index if available
            try:
                from nexaura.backend.search.bm25 import BM25Index
                bm25_path = self.config.bm25_index_path
                self.bm25_index = BM25Index(index_path=bm25_path)
                if bm25_path and Path(bm25_path).exists():
                    self.bm25_index.load()
            except Exception as exc:
                logger.warning("BM25 index load failed: %s", exc)

    def run(self) -> ProcessingReport:
        """
        Execute the complete ingestion pipeline.

        Returns:
            ProcessingReport with all statistics.
        """
        from nexaura.backend.ingestion.graph_builder import GraphBuilder
        from nexaura.backend.acquisition import InventoryManager, BISIngestionConnector, AccessStatus, ProcessingStatus

        self._graph_builder = GraphBuilder()
        self.inventory_manager = InventoryManager(output_dir=self.config.output_dir)
        self.crossref_connector = BISIngestionConnector()

        # Pre-populate from bis_ingestion read-only records if available
        for rec in self.crossref_connector.discover_all_records():
            std_num = rec.get("standard_number") or rec.get("is_number") or "unknown"
            title = rec.get("title") or rec.get("standard_title") or "Untitled Standard"
            doc_id = f"BIS_REC_{std_num}"
            self.inventory_manager.register_document(
                document_id=doc_id,
                title=title,
                standard_number=std_num,
                source_pdf=rec.get("pdf_url") or rec.get("source_url"),
                access_status=AccessStatus.METADATA_ONLY,
                processing_status=ProcessingStatus.PENDING,
            )

        # Collect PDFs to process
        if self.config.specific_pdf:
            pdf_files = [self.config.specific_pdf]
        else:
            pdf_files = sorted(self.config.input_dir.rglob("*.pdf"))

        self.report.total_pdfs = len(pdf_files)
        logger.info("Pipeline starting: %d PDFs to process", len(pdf_files))

        # Track all knowledge units for BM25/embedding batch
        all_knowledge_units: list = []

        # Initialize JSONL output files
        clauses_path  = self.config.output_dir / "clauses.jsonl"
        tables_path   = self.config.output_dir / "tables.jsonl"
        docs_path     = self.config.output_dir / "documents.jsonl"
        features_path = self.config.output_dir / "features.jsonl"

        processor = PDFProcessor(self.config)
        start_time = time.time()

        for pdf_path in pdf_files:
            # Resume check
            if self.config.resume and not self.config.force and self.repository:
                import xxhash
                h = xxhash.xxh64()
                with open(pdf_path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                file_hash = h.hexdigest()
                if self.repository.is_already_processed(file_hash):
                    logger.info("Skipping (already processed): %s", pdf_path.name)
                    self.report.skipped_pdfs += 1
                    continue

            # Mark as processing
            if self.repository:
                try:
                    file_hash = processor.pdf_detector._hash_file(pdf_path)
                    self.repository.log_processing_start(pdf_path.name, file_hash)
                except Exception:
                    file_hash = ""
            else:
                file_hash = ""

            # Process the PDF
            result = processor.process(pdf_path)

            if result["success"]:
                knowledge_units = result["knowledge_units"]
                tables = result["tables"]
                meta = result["metadata"]

                # Update report
                self.report.processed_pdfs += 1
                self.report.total_pages    += result["total_pages"]
                self.report.gemini_pages   += result["gemini_pages"]
                self.report.total_clauses  += result["clauses_extracted"]
                self.report.total_tables   += result["tables_extracted"]
                self.report.total_features += result["features_extracted"]
                self.report.flagged_records+= result["flagged_records"]

                # Update PDF type counters
                pdf_type = result.get("pdf_type", "")
                if pdf_type == "text_pdf":
                    self.report.text_pdfs += 1
                elif pdf_type == "scanned_pdf":
                    self.report.scanned_pdfs += 1
                else:
                    self.report.mixed_pdfs += 1

                # === Write JSONL outputs ===
                self._append_jsonl(clauses_path, [ku.model_dump() for ku in knowledge_units])
                self._append_jsonl(tables_path, [self._table_to_dict(t) for t in tables])
                self._append_jsonl(docs_path, [{
                    "pdf_name": result["pdf_name"],
                    "standard_number": meta.standard_number if meta else "unknown",
                    "title": meta.title if meta else None,
                    "clauses": result["clauses_extracted"],
                    "tables": result["tables_extracted"],
                }])

                # Features JSONL
                features_rows = []
                for ku in knowledge_units:
                    for param in ku.technical_parameters:
                        features_rows.append({
                            "knowledge_unit_id": ku.id,
                            "standard_number": ku.standard_number,
                            "clause": ku.clause,
                            **param.model_dump(),
                        })
                self._append_jsonl(features_path, features_rows)

                # === Document Inventory Registration ===
                std_num = (meta.standard_number if (meta and meta.standard_number) else None) or "unknown"
                std_title = (meta.title if (meta and meta.title) else None) or pdf_path.stem or "Untitled Document"
                self.inventory_manager.register_document(
                    document_id=pdf_path.stem,
                    title=std_title,
                    standard_number=std_num,
                    source_pdf=pdf_path.name,
                    file_hash=file_hash,
                    file_size=pdf_path.stat().st_size,
                    access_status=AccessStatus.DOWNLOADED,
                    processing_status=ProcessingStatus.COMPLETED,
                    parent_standard_id=f"STD_{std_num}",
                )

                # === Database inserts ===
                if self.repository and meta:
                    try:
                        std_id = self.repository.upsert_standard(
                            meta.standard_number, meta.title, meta.status, pdf_path.name
                        )
                        ed_id = self.repository.upsert_edition(
                            std_id, meta.edition, meta.year, meta.scope, meta.foreword
                        )
                        self.repository.batch_insert_clauses(knowledge_units, std_id, ed_id)
                        self.repository.insert_features(knowledge_units, meta.standard_number)
                        self.repository.insert_relationships(std_id, meta)
                        for t in tables:
                            self.repository.upsert_table(t, std_id)
                        self.repository.upsert_source(
                            std_id, pdf_path.name, file_hash,
                            pdf_path.stat().st_size, result["total_pages"],
                            result["total_pages"], result["gemini_pages"], result["text_pages"],
                        )
                        self.repository.log_processing_complete(
                            file_hash, result["clauses_extracted"],
                            result["tables_extracted"], result["features_extracted"],
                            result["avg_confidence"],
                        )
                    except Exception as exc:
                        logger.error("DB insert failed for %s: %s", pdf_path.name, exc)

                # === Knowledge Graph ===
                if meta:
                    self._graph_builder.add_document(meta, knowledge_units)

                # Collect for batch embedding
                all_knowledge_units.extend(knowledge_units)

            else:
                self.report.failed_pdfs += 1
                self.report.errors.append(f"{pdf_path.name}: {result.get('error', 'Unknown error')}")
                if self.repository and file_hash:
                    self.repository.log_processing_failed(file_hash, result.get("error", ""))

        # === Batch Embeddings (after all PDFs) ===
        if all_knowledge_units and self.embedding_service and not self.config.skip_embeddings:
            self._generate_and_store_embeddings(all_knowledge_units)

        # === Save BM25 Index ===
        if self.bm25_index and all_knowledge_units and not self.config.skip_embeddings:
            try:
                # Rebuild with all units (including from previous runs if loaded from DB)
                self.bm25_index.build(all_knowledge_units)
                if self.config.bm25_index_path:
                    self.bm25_index.save()
            except Exception as exc:
                logger.error("BM25 index save failed: %s", exc)

        # === Save Knowledge Graph ===
        if self._graph_builder and self.config.knowledge_graph_path:
            try:
                self._graph_builder.save(self.config.knowledge_graph_path)
            except Exception as exc:
                logger.error("Knowledge graph save failed: %s", exc)

        # === Export Inventory & Coverage Reports ===
        try:
            report_paths = self.inventory_manager.export_reports()
            logger.info("Exported inventory reports: %s", report_paths)
            if self.repository and hasattr(self.repository, "save_inventory_and_coverage"):
                with open(report_paths["documents_inventory"], "r", encoding="utf-8") as f1:
                    inv_pay = json.load(f1)
                with open(report_paths["document_coverage_report"], "r", encoding="utf-8") as f2:
                    cov_pay = json.load(f2)
                self.repository.save_inventory_and_coverage(inv_pay, cov_pay)
        except Exception as exc:
            logger.error("Failed to export document inventory reports: %s", exc)

        # === Finalize Report ===
        elapsed = time.time() - start_time
        self.report.processing_time_seconds = elapsed
        self.report.finished_at = datetime.now(timezone.utc).isoformat()
        self.report.total_embeddings = len(all_knowledge_units)

        # Save processing report
        if self.config.processing_report_path:
            self._save_report()

        self._print_summary()
        return self.report

    # -------------------------------------------------------------------------
    # Embedding generation
    # -------------------------------------------------------------------------

    def _generate_and_store_embeddings(self, knowledge_units: list) -> None:
        """Generate embeddings and upsert to Qdrant."""
        logger.info("Generating embeddings for %d knowledge units...", len(knowledge_units))
        try:
            vectors = self.embedding_service.embed_knowledge_units(knowledge_units)
            if self.qdrant_manager and vectors:
                self.qdrant_manager.upsert_vectors(knowledge_units, vectors)
                self.report.total_embeddings = len(vectors)
                logger.info("Embeddings stored: %d vectors", len(vectors))
        except Exception as exc:
            logger.error("Embedding generation failed: %s", exc)

    # -------------------------------------------------------------------------
    # Output helpers
    # -------------------------------------------------------------------------

    def _append_jsonl(self, path: Path, records: list[dict]) -> None:
        """Append records to a JSONL file."""
        if not records:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _table_to_dict(self, table) -> dict:
        """Convert TableRecord to dict for JSONL output."""
        return {
            "table_id":         table.table_id,
            "source_table_ref": table.source_table_ref,
            "clause":           table.clause,
            "page":             table.page,
            "caption":          table.caption,
            "columns":          table.columns,
            "rows":             table.rows,
            "units":            table.units,
            "footnotes":        table.footnotes,
            "search_text":      table.search_text,
            "source_pdf":       table.source_pdf,
            "standard_number":  table.standard_number,
            "needs_review":     table.needs_review,
        }

    def _save_report(self) -> None:
        """Save processing report to JSON."""
        path = self.config.processing_report_path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.report.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Processing report saved: %s", path)

    def _print_summary(self) -> None:
        """Print a summary to the terminal."""
        r = self.report
        print("\n" + "=" * 70)
        print("  NEXAURA PIPELINE COMPLETE")
        print("=" * 70)
        print(f"  Total PDFs:        {r.total_pdfs}")
        print(f"  Processed:         {r.processed_pdfs}")
        print(f"  Failed:            {r.failed_pdfs}")
        print(f"  Skipped (resume):  {r.skipped_pdfs}")
        print(f"  Total Pages:       {r.total_pages}")
        print(f"  Gemini Pages:      {r.gemini_pages}")
        print(f"  Clauses:           {r.total_clauses}")
        print(f"  Tables:            {r.total_tables}")
        print(f"  Features:          {r.total_features}")
        print(f"  Embeddings:        {r.total_embeddings}")
        print(f"  Flagged Records:   {r.flagged_records}")
        print(f"  Processing Time:   {r.processing_time_seconds:.1f}s")
        if r.errors:
            print(f"\n  ERRORS ({len(r.errors)}):")
            for e in r.errors[:5]:
                print(f"    - {e}")
        print("=" * 70 + "\n")

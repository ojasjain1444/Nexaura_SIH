"""
inventory_manager.py — BIS Document Acquisition & Inventory Manager

Project: Nexaura (SIH 2026 — SIH26107)

Manages:
    - Multi-document classification (A-P categories)
    - Document versioning & deduplication (hash tracking)
    - Directed Relationship Mapping (HAS_AMENDMENT, HAS_STI, HAS_PRODUCT_MANUAL, etc.)
    - Per-Standard Completeness Auditing
    - Inventory Export (documents_inventory.json & document_coverage_report.json)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from nexaura.backend.acquisition.document_models import (
    AccessStatus,
    CompletenessAudit,
    DocumentMetadata,
    DocumentRelationship,
    DocumentType,
    InventorySummary,
    ProcessingStatus,
    RelationType,
)

logger = logging.getLogger(__name__)


class InventoryManager:
    """
    Central manager for BIS document acquisition, classification, inventory,
    and completeness coverage reporting.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._documents: Dict[str, DocumentMetadata] = {}
        self._relationships: List[DocumentRelationship] = []
        self._audits: Dict[str, CompletenessAudit] = {}

    def classify_filename_and_meta(
        self, filename: str, metadata_title: Optional[str] = None
    ) -> DocumentType:
        """Classify a document into one of categories A-P based on filename and title rules."""
        fn = filename.lower()
        title = (metadata_title or "").lower()

        if "amendment" in fn or "amd" in fn or "amendment" in title:
            return DocumentType.AMENDMENT
        if "corrigendum" in fn or "corr" in fn or "corrigendum" in title:
            return DocumentType.CORRIGENDUM
        if "addendum" in fn or "addendum" in title:
            return DocumentType.ADDENDUM
        if "product manual" in fn or "pm_" in fn or "product manual" in title:
            return DocumentType.PRODUCT_MANUAL
        if "sti" in fn or "scheme of testing" in title or "sti_" in fn:
            return DocumentType.STI
        if "qco" in fn or "quality control order" in title:
            return DocumentType.QCO
        if "gazette" in fn or "gazette" in title:
            return DocumentType.GAZETTE_NOTIFICATION
        if "hallmark" in fn or "hallmarking" in title:
            return DocumentType.HALLMARKING
        if "guideline" in fn or "guidance" in title:
            return DocumentType.GUIDELINE
        if "lab" in fn or "laboratory" in title:
            return DocumentType.LABORATORY
        if "draft" in fn or "draft" in title:
            return DocumentType.DRAFT_STANDARD
        if "withdrawn" in fn or "superseded" in title:
            return DocumentType.WITHDRAWN_STANDARD

        if re.search(r"is[_\s]?\d+", fn) or re.search(r"is[_\s]?\d+", title):
            return DocumentType.MAIN_STANDARD

        return DocumentType.UNKNOWN

    def register_document(
        self,
        document_id: str,
        title: str,
        standard_number: str = "unknown",
        doc_type: Optional[DocumentType] = None,
        source_pdf: Optional[str] = None,
        file_hash: Optional[str] = None,
        file_size: int = 0,
        access_status: AccessStatus = AccessStatus.DOWNLOADED,
        processing_status: ProcessingStatus = ProcessingStatus.COMPLETED,
        parent_standard_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentMetadata:
        """Register a document into the central inventory tracking."""
        if doc_type is None or doc_type == DocumentType.UNKNOWN:
            doc_type = self.classify_filename_and_meta(source_pdf or document_id, title)

        clean_title = (title or "").strip() or source_pdf or document_id or "Untitled Document"

        doc = DocumentMetadata(
            document_id=document_id,
            document_type=doc_type,
            title=clean_title,
            standard_number=standard_number,
            source_url=source_pdf,
            mime_type="application/pdf" if (source_pdf and source_pdf.endswith(".pdf")) else "text/html",
            file_size=file_size,
            xxhash=file_hash,
            parent_standard_id=parent_standard_id,
            access_status=access_status,
            processing_status=processing_status,
            extra_metadata=extra_metadata or {},
        )

        self._documents[document_id] = doc

        # Register auto-relationships
        if parent_standard_id and parent_standard_id != document_id:
            rel_type = RelationType.RELATED_TO
            if doc_type == DocumentType.AMENDMENT:
                rel_type = RelationType.HAS_AMENDMENT
            elif doc_type == DocumentType.CORRIGENDUM:
                rel_type = RelationType.HAS_CORRIGENDUM
            elif doc_type == DocumentType.PRODUCT_MANUAL:
                rel_type = RelationType.HAS_PRODUCT_MANUAL
            elif doc_type == DocumentType.STI:
                rel_type = RelationType.HAS_STI
            elif doc_type == DocumentType.GUIDELINE:
                rel_type = RelationType.HAS_GUIDELINE
            elif doc_type == DocumentType.QCO:
                rel_type = RelationType.HAS_QCO

            self.add_relationship(
                from_id=parent_standard_id,
                to_id=document_id,
                relation_type=rel_type,
            )

        # Update per-standard completeness audit
        self._update_audit(standard_number, doc)

        return doc

    def add_relationship(
        self, from_id: str, to_id: str, relation_type: RelationType, source_evidence: str = "document_metadata"
    ) -> DocumentRelationship:
        """Add an explicit relationship between standards, products, or documents."""
        rel = DocumentRelationship(
            from_id=from_id,
            to_id=to_id,
            relation_type=relation_type,
            source_evidence=source_evidence,
        )
        self._relationships.append(rel)
        return rel

    def _update_audit(self, standard_number: str, doc: DocumentMetadata) -> None:
        """Update the completeness audit report for a given standard."""
        if standard_number not in self._audits:
            self._audits[standard_number] = CompletenessAudit(
                standard_number=standard_number,
                expected_documents=["Main Standard", "Amendment(s)", "Product Manual", "STI"],
            )

        audit = self._audits[standard_number]
        audit.discovered_documents += 1

        if doc.access_status == AccessStatus.DOWNLOADED:
            audit.downloaded_documents += 1
        elif doc.access_status == AccessStatus.METADATA_ONLY:
            audit.metadata_only_documents += 1
        elif doc.access_status == AccessStatus.FAILED:
            audit.failed_documents += 1

        dt_key = doc.document_type.value
        audit.document_breakdown[dt_key] = audit.document_breakdown.get(dt_key, 0) + 1

        if audit.failed_documents > 0:
            audit.availability = "partial"
        elif audit.downloaded_documents > 0:
            audit.availability = "complete"
        elif audit.metadata_only_documents > 0:
            audit.availability = "metadata_only"
        else:
            audit.availability = "not_publicly_available"

    def generate_inventory_summary(self) -> InventorySummary:
        """Compute aggregate summary metrics across all registered documents."""
        summary = InventorySummary()
        summary.total_documents_discovered = len(self._documents)

        for doc in self._documents.values():
            if doc.mime_type == "application/pdf":
                summary.total_pdfs_discovered += 1
                if doc.access_status == AccessStatus.DOWNLOADED:
                    summary.total_pdfs_downloaded += 1
                if doc.processing_status == ProcessingStatus.COMPLETED:
                    summary.total_pdfs_processed += 1
            elif doc.mime_type == "text/html":
                summary.total_html_pages += 1

            if doc.access_status == AccessStatus.METADATA_ONLY:
                summary.total_metadata_only += 1
            elif doc.access_status == AccessStatus.FAILED:
                summary.total_failed += 1

            dt = doc.document_type
            if dt == DocumentType.AMENDMENT:
                summary.total_amendments += 1
            elif dt == DocumentType.CORRIGENDUM:
                summary.total_corrigenda += 1
            elif dt == DocumentType.PRODUCT_MANUAL:
                summary.total_product_manuals += 1
            elif dt == DocumentType.STI:
                summary.total_STIs += 1
            elif dt == DocumentType.QCO:
                summary.total_QCO_documents += 1
            elif dt == DocumentType.GAZETTE_NOTIFICATION:
                summary.total_notifications += 1
            elif dt == DocumentType.GUIDELINE:
                summary.total_guidelines += 1
            elif dt == DocumentType.HALLMARKING:
                summary.total_Hallmarking_documents += 1
            elif dt == DocumentType.MANAGEMENT_SYSTEM:
                summary.total_management_system_documents += 1
            elif dt == DocumentType.LABORATORY:
                summary.total_laboratory_documents += 1
            elif dt in (DocumentType.CERTIFICATION_SCHEME, DocumentType.LICENCE):
                summary.total_certification_documents += 1

        return summary

    def export_reports(self) -> Dict[str, Path]:
        """
        Export documents_inventory.json and document_coverage_report.json to output_dir.
        """
        inv_path = self.output_dir / "documents_inventory.json"
        cov_path = self.output_dir / "document_coverage_report.json"

        summary = self.generate_inventory_summary()

        inventory_payload = {
            "summary": summary.model_dump(),
            "documents": [doc.model_dump() for doc in self._documents.values()],
            "relationships": [rel.model_dump() for rel in self._relationships],
        }

        with open(inv_path, "w", encoding="utf-8") as f:
            json.dump(inventory_payload, f, ensure_ascii=False, indent=2)

        coverage_payload = {
            "total_standards_audited": len(self._audits),
            "coverage": [audit.model_dump() for audit in self._audits.values()],
        }

        with open(cov_path, "w", encoding="utf-8") as f:
            json.dump(coverage_payload, f, ensure_ascii=False, indent=2)

        logger.info("Exported documents_inventory.json (%d docs)", len(self._documents))
        logger.info("Exported document_coverage_report.json (%d standards)", len(self._audits))

        return {
            "documents_inventory": inv_path,
            "document_coverage_report": cov_path,
        }

"""
test_acquisition.py — Automated Tests for BIS Document Acquisition & Inventory Engine
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexaura.backend.acquisition import (
    AccessStatus,
    DocumentType,
    InventoryManager,
    ProcessingStatus,
    RelationType,
)


def test_classification():
    mgr = InventoryManager(output_dir=PROJECT_ROOT / "nexaura" / "data" / "processed")
    assert mgr.classify_filename_and_meta("IS_456_2000_amd_1.pdf") == DocumentType.AMENDMENT
    assert mgr.classify_filename_and_meta("STI_IS_10500.pdf") == DocumentType.STI
    assert mgr.classify_filename_and_meta("PM_IS_2062.pdf") == DocumentType.PRODUCT_MANUAL
    assert mgr.classify_filename_and_meta("QCO_steel.pdf") == DocumentType.QCO
    assert mgr.classify_filename_and_meta("IS_10500_2012.pdf") == DocumentType.MAIN_STANDARD
    print("✓ Document classification test passed.")


def test_inventory_and_reports():
    output_dir = PROJECT_ROOT / "nexaura" / "data" / "processed"
    mgr = InventoryManager(output_dir=output_dir)

    # Register main standard
    mgr.register_document(
        document_id="IS_10500_2012",
        title="Drinking Water Standard",
        standard_number="IS 10500:2012",
        doc_type=DocumentType.MAIN_STANDARD,
        source_pdf="IS_10500_2012.pdf",
        access_status=AccessStatus.DOWNLOADED,
        processing_status=ProcessingStatus.COMPLETED,
    )

    # Register amendment
    mgr.register_document(
        document_id="IS_10500_AMD_1",
        title="Amendment No 1 to IS 10500",
        standard_number="IS 10500:2012",
        doc_type=DocumentType.AMENDMENT,
        source_pdf="IS_10500_AMD_1.pdf",
        access_status=AccessStatus.DOWNLOADED,
        processing_status=ProcessingStatus.COMPLETED,
        parent_standard_id="IS_10500_2012",
    )

    # Export reports
    paths = mgr.export_reports()
    assert paths["documents_inventory"].exists()
    assert paths["document_coverage_report"].exists()

    with open(paths["documents_inventory"], "r", encoding="utf-8") as f:
        inv_data = json.load(f)
    assert inv_data["summary"]["total_documents_discovered"] == 2
    assert inv_data["summary"]["total_amendments"] == 1

    with open(paths["document_coverage_report"], "r", encoding="utf-8") as f:
        cov_data = json.load(f)
    assert cov_data["total_standards_audited"] == 1
    assert cov_data["coverage"][0]["downloaded_documents"] == 2

    print("✓ Inventory & coverage export test passed.")


if __name__ == "__main__":
    test_classification()
    test_inventory_and_reports()

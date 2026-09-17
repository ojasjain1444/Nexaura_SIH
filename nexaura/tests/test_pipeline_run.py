"""
test_pipeline_run.py — Dry-run verification test for PDF ingestion & MongoDB pipeline
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexaura.backend.ingestion.pipeline import PipelineConfig, NexauraPipeline


def test_dry_run():
    input_dir = PROJECT_ROOT / "nexaura" / "data" / "raw"
    output_dir = PROJECT_ROOT / "nexaura" / "data" / "processed"

    pdfs = list(input_dir.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in data/raw for testing.")
        return

    test_pdf = pdfs[0]
    print(f"Testing ingestion pipeline on: {test_pdf.name}")

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        workers=1,
        resume=False,
        force=True,
        skip_ocr=True,  # Test text extraction pipeline
        skip_embeddings=True,
        specific_pdf=test_pdf,
        mongo_url="mongodb://localhost:27017",
        mongo_db_name="KnowledgeBase",
    )

    pipeline = NexauraPipeline(config)
    report = pipeline.run()

    print("\n--- Pipeline Dry-Run Results ---")
    print(f"Processed PDFs: {report.processed_pdfs}")
    print(f"Total Clauses: {report.total_clauses}")
    print(f"Total Features: {report.total_features}")
    print(f"Total Tables: {report.total_tables}")
    assert report.processed_pdfs == 1, "Pipeline failed to process test PDF"
    print("✓ End-to-end dry-run completed successfully!")


if __name__ == "__main__":
    test_dry_run()

"""
ingest.py — Nexaura BIS PDF Ingestion CLI

Project: Nexaura (SIH 2026 — SIH26107)

Usage:
    python scripts/ingest.py --input nexaura/data/raw --output nexaura/data/processed

    # Process a single PDF:
    python scripts/ingest.py --pdf nexaura/data/raw/IS456.pdf

    # Force reprocess (ignore cache):
    python scripts/ingest.py --input nexaura/data/raw --force

    # Skip embeddings (Qdrant/BM25):
    python scripts/ingest.py --input nexaura/data/raw --skip-embeddings

    # Text extraction only (no Gemini):
    python scripts/ingest.py --input nexaura/data/raw --skip-ocr

    # Similarity search test after processing:
    python scripts/ingest.py --search "galvanized steel pipe coating thickness"
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure the project root is in Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present
try:
    from dotenv import load_dotenv
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"[ENV] Loaded: {env_file}")
except ImportError:
    pass


def setup_logging(level: str = "INFO", log_file: Path = None) -> None:
    """Configure logging for CLI output."""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )
    # Reduce noise from external libraries
    for lib in ("httpx", "httpcore", "urllib3", "sentence_transformers"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def build_config(args: argparse.Namespace):
    """Build PipelineConfig from parsed CLI arguments."""
    from nexaura.backend.ingestion.pipeline import PipelineConfig

    input_dir  = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    # Derive standard paths from output dir
    data_dir = output_dir.parent

    return PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        workers=args.workers,
        resume=not args.no_resume,
        force=args.force,
        skip_ocr=args.skip_ocr,
        skip_embeddings=args.skip_embeddings,
        specific_pdf=Path(args.pdf).resolve() if args.pdf else None,

        # API keys from environment (never from CLI)
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),

        mongo_url=os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URL", "mongodb://localhost:27017"),
        mongo_db_name=os.environ.get("MONGO_DB_NAME", "KnowledgeBase"),
        postgres_url=os.environ.get("POSTGRES_URL"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),

        embedding_provider="sentence_transformers",
        embedding_model="all-MiniLM-L6-v2",

        bm25_index_path=data_dir / "embeddings" / "bm25_index.pkl",
        knowledge_graph_path=output_dir / "knowledge_graph.json",
        processing_report_path=output_dir / "processing_report.json",
        failed_log_path=data_dir / "logs" / "failed_files.jsonl",
        low_confidence_log_path=data_dir / "logs" / "low_confidence.jsonl",
        cache_dir=data_dir / "cache" / "gemini",
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run the ingestion pipeline."""
    config = build_config(args)

    # Validate input
    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"[ERROR] PDF not found: {pdf_path}", file=sys.stderr)
            return 1
    else:
        if not config.input_dir.exists():
            print(f"[ERROR] Input directory not found: {config.input_dir}", file=sys.stderr)
            return 1
        pdfs = list(config.input_dir.rglob("*.pdf"))
        if not pdfs:
            print(f"[WARNING] No PDF files found in: {config.input_dir}")
            return 0

    print(f"\n{'='*60}")
    print("  NEXAURA BIS KNOWLEDGE BASE BUILDER")
    print(f"{'='*60}")
    print(f"  Input:     {config.input_dir}")
    print(f"  Output:    {config.output_dir}")
    print(f"  Workers:   {config.workers}")
    print(f"  Resume:    {config.resume}")
    print(f"  Force:     {config.force}")
    print(f"  Skip OCR:  {config.skip_ocr}")
    print(f"  Skip Emb:  {config.skip_embeddings}")
    if args.pdf:
        print(f"  PDF:       {args.pdf}")
    print(f"{'='*60}\n")

    from nexaura.backend.ingestion.pipeline import NexauraPipeline
    pipeline = NexauraPipeline(config)
    report = pipeline.run()

    return 0 if report.failed_pdfs == 0 else 1


def cmd_search(args: argparse.Namespace) -> int:
    """Run a similarity search query against the knowledge base."""
    query = args.search
    top_k = args.top_k
    output_dir = Path(args.output).resolve()
    data_dir = output_dir.parent

    print(f"\nSearching for: '{query}'")
    print(f"Top-K: {top_k}\n")

    try:
        # Load BM25 index
        from nexaura.backend.search.bm25 import BM25Index
        bm25_path = data_dir / "embeddings" / "bm25_index.pkl"
        bm25 = BM25Index(index_path=bm25_path)
        bm25_loaded = bm25.load()

        if not bm25_loaded:
            print("[INFO] BM25 index not found. Run ingestion first.")
            return 1

        # BM25-only search (no Qdrant/embeddings needed for quick test)
        results = bm25.search(query, top_k=top_k)

        if not results:
            print("No results found.")
            return 0

        print(f"{'='*70}")
        print(f"  BM25 SEARCH RESULTS")
        print(f"{'='*70}")
        for r in results:
            meta = r.get("metadata", {})
            print(f"\n  [{r['rank']}] Score: {r['score']:.4f}")
            print(f"       Standard:  {meta.get('standard_number', 'N/A')}")
            print(f"       Clause:    {meta.get('clause', 'N/A')}")
            print(f"       Heading:   {meta.get('heading', 'N/A')}")
            print(f"       Page:      {meta.get('page_start', 'N/A')}")
            print(f"       Source:    {meta.get('source_pdf', 'N/A')}")
        print(f"\n{'='*70}\n")

        return 0

    except Exception as exc:
        print(f"[ERROR] Search failed: {exc}", file=sys.stderr)
        return 1


def cmd_detect(args: argparse.Namespace) -> int:
    """Analyse a single PDF without processing it."""
    pdf_path = Path(args.detect).resolve()
    if not pdf_path.exists():
        print(f"[ERROR] File not found: {pdf_path}", file=sys.stderr)
        return 1

    from nexaura.backend.ingestion.pdf_detector import PDFDetector
    detector = PDFDetector()
    result = detector.analyse(pdf_path)

    print(f"\n{'='*60}")
    print(f"  PDF ANALYSIS: {pdf_path.name}")
    print(f"{'='*60}")
    print(f"  Type:         {result.pdf_type.value}")
    print(f"  Valid:        {result.is_valid}")
    print(f"  Total Pages:  {result.total_pages}")
    print(f"  Text Pages:   {result.text_pages}")
    print(f"  Scanned:      {result.scanned_pages}")
    print(f"  Mixed:        {result.mixed_pages}")
    print(f"  Blank:        {result.blank_pages}")
    print(f"  Gemini Needed:{result.pages_requiring_gemini}")
    print(f"  File Hash:    {result.file_hash}")
    print(f"  Size:         {result.file_size_bytes / 1024:.1f} KB")

    if result.error_message:
        print(f"\n  [ERROR] {result.error_message}")

    print(f"\n  First 5 pages:")
    for page in result.pages[:5]:
        print(
            f"    Page {page.page_number:3d}: {page.page_type.value:<14} "
            f"text={page.text_length:5d} chars  images={page.image_count}"
            f"  {'→ GEMINI' if page.requires_gemini else '→ direct'}"
        )
    print(f"{'='*60}\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Nexaura BIS Knowledge Base Builder — PDF Ingestion CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs in data/raw:
  python scripts/ingest.py --input nexaura/data/raw --output nexaura/data/processed

  # Process a single PDF:
  python scripts/ingest.py --pdf nexaura/data/raw/IS456.pdf

  # Analyse a PDF without processing:
  python scripts/ingest.py --detect nexaura/data/raw/IS456.pdf

  # Test similarity search:
  python scripts/ingest.py --search "galvanized steel pipe coating thickness"

  # Force reprocess all (ignore cache):
  python scripts/ingest.py --input nexaura/data/raw --force

  # Skip OCR and Gemini (text extraction only):
  python scripts/ingest.py --input nexaura/data/raw --skip-ocr
        """,
    )

    # Core arguments
    parser.add_argument("--input", "-i", default="nexaura/data/raw",
                        help="Input directory containing BIS PDFs (default: nexaura/data/raw)")
    parser.add_argument("--output", "-o", default="nexaura/data/processed",
                        help="Output directory for processed data (default: nexaura/data/processed)")
    parser.add_argument("--pdf", "-p", default=None,
                        help="Process a single specific PDF file")
    parser.add_argument("--workers", "-w", type=int, default=1,
                        help="Number of parallel worker processes (default: 1)")

    # Resume and force
    parser.add_argument("--no-resume", action="store_true",
                        help="Disable resume — reprocess all PDFs")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force reprocess even if cached (implies --no-resume)")

    # Pipeline control
    parser.add_argument("--skip-ocr", action="store_true",
                        help="Skip Gemini OCR — use text extraction only")
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip embedding generation and Qdrant/BM25")
    parser.add_argument("--gemini-validation", action="store_true",
                        help="Run extra Gemini validation pass on extracted data")

    # Search
    parser.add_argument("--search", "-s", default=None,
                        help="Run a similarity search query (requires processed data)")
    parser.add_argument("--top-k", "-k", type=int, default=10,
                        help="Number of search results (default: 10)")

    # Analysis
    parser.add_argument("--detect", "-d", default=None,
                        help="Analyse a PDF without processing it")

    # Logging
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log level (default: INFO)")

    args = parser.parse_args()

    # Setup logging
    output_dir = Path(args.output).resolve()
    log_file = output_dir.parent / "logs" / "ingestion.log"
    setup_logging(args.log_level, log_file)

    # Dispatch commands
    if args.detect:
        sys.exit(cmd_detect(args))
    elif args.search:
        sys.exit(cmd_search(args))
    else:
        sys.exit(cmd_ingest(args))


if __name__ == "__main__":
    main()

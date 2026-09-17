"""
__main__.py — CLI entry point for the BIS ingestion pipeline.

Usage:
    python -m bis_ingestion               # full pipeline (test mode)
    python -m bis_ingestion --full        # full pipeline (no record limit)
    python -m bis_ingestion --lims-only   # LIMS crawl only
    python -m bis_ingestion --std-only    # Standards Portal crawl only
    python -m bis_ingestion --export      # Export DB to CSV/JSON/JSONL
    python -m bis_ingestion --chunk       # Generate RAG chunks from DB
    python -m bis_ingestion --is-start 1 --is-end 100  # Custom LIMS IS range
"""

from __future__ import annotations

import argparse
import json
import sys

from bis_ingestion.pipeline import (
    run_export,
    run_full_pipeline,
    run_lims_crawl,
    run_rag_chunking,
    run_standards_crawl,
    setup_logging,
)
from bis_ingestion.storage import BISDatabase


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m bis_ingestion",
        description=(
            "Nexaura BIS Standards Ingestion Pipeline\n"
            "Collects publicly accessible BIS metadata from official government portals."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full",
        action="store_true",
        help="Run full pipeline without record limits (production crawl)",
    )
    mode.add_argument(
        "--lims-only",
        action="store_true",
        help="Run LIMS crawl only",
    )
    mode.add_argument(
        "--std-only",
        action="store_true",
        help="Run Standards Portal crawl only",
    )
    mode.add_argument(
        "--export",
        action="store_true",
        help="Export existing database to CSV / JSON / JSONL",
    )
    mode.add_argument(
        "--chunk",
        action="store_true",
        help="Generate RAG chunks from the existing database",
    )

    parser.add_argument(
        "--is-start",
        type=int,
        default=None,
        metavar="N",
        help="First IS document number for LIMS sequential crawl (default: from config)",
    )
    parser.add_argument(
        "--is-end",
        type=int,
        default=None,
        metavar="N",
        help="Last IS document number for LIMS sequential crawl (default: from config)",
    )
    parser.add_argument(
        "--query",
        type=str,
        action="append",
        metavar="TERM",
        help="Add a search query for the Standards Portal (can be repeated)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity (default: INFO)",
    )

    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    setup_logging(level=args.log_level)

    from bis_ingestion.config import LIMS_IS_END, LIMS_IS_START

    is_start = args.is_start or LIMS_IS_START
    is_end = args.is_end or LIMS_IS_END

    if args.export:
        with BISDatabase() as db:
            paths = run_export(db)
        print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
        return 0

    if args.chunk:
        with BISDatabase() as db:
            n = run_rag_chunking(db)
        print(f"Generated {n} RAG chunks")
        return 0

    if args.lims_only:
        with BISDatabase() as db:
            n = run_lims_crawl(db, is_start=is_start, is_end=is_end)
        print(f"LIMS crawl complete: {n} records")
        return 0

    if args.std_only:
        with BISDatabase() as db:
            n = run_standards_crawl(
                db,
                queries=args.query,
            )
        print(f"Standards crawl complete: {n} records")
        return 0

    # Default: full pipeline
    summary = run_full_pipeline(
        test_mode=not args.full,
        run_lims=True,
        run_standards=True,
        lims_is_start=is_start,
        lims_is_end=is_end,
        standards_queries=args.query,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0 if not summary.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())

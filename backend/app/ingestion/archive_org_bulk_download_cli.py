"""
Developer CLI for downloading many real Indian Standards from Internet
Archive's public index (see app/ingestion/archive_org_client.py for why
this is a legitimate, unauthenticated public API — not a workaround for
BIS's own gated portal).

Usage:
    python -m app.ingestion.archive_org_bulk_download_cli <output_folder> --query "water" --limit 50
    python -m app.ingestion.archive_org_bulk_download_cli <output_folder> --identifiers-file ids.txt

This only downloads PDFs to a local folder — it does not ingest them. Run
app.ingestion.bulk_ingest_cli against the same folder afterward (or pass
--ingest to do both in one step) to actually process them into the
database, exactly as if they had been uploaded through the UI one at a
time. Kept as two separate steps by default because downloading a large
batch and then reviewing/ingesting it are legitimately separate actions
(e.g. spot-checking a sample of PDFs before committing to a large ingest).

Sequential, one request at a time, with no retry-storming (see
DELAY_BETWEEN_DOWNLOADS_SECONDS) — deliberately conservative out of respect
for a free, donation-funded nonprofit service, not a performance
limitation of this code.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from app.ingestion.archive_org_client import ArchiveOrgError, fetch_pdf, search_standards

DELAY_BETWEEN_DOWNLOADS_SECONDS = 1.0


def _safe_filename(identifier: str) -> str:
    return f"{identifier}.pdf"


def run(output_folder: str, query: str | None, identifiers: list[str] | None, limit: int, do_ingest: bool) -> int:
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    if identifiers:
        targets = [(identifier, identifier) for identifier in identifiers]
    else:
        if not query:
            print("Must pass either --query or --identifiers-file")
            return 1
        results = search_standards(query, max_results=limit)
        if not results:
            print(f"No standards found on Internet Archive matching {query!r}")
            return 1
        targets = [(r.identifier, r.title) for r in results]

    print(f"Downloading {len(targets)} standard(s) to {out_dir}\n")

    succeeded, skipped, failed = 0, 0, 0
    for i, (identifier, title) in enumerate(targets, start=1):
        dest = out_dir / _safe_filename(identifier)
        print(f"[{i}/{len(targets)}] {identifier} — {title}", flush=True)
        if dest.exists():
            print("  -> SKIPPED (already downloaded)")
            skipped += 1
            continue
        try:
            pdf_bytes = fetch_pdf(identifier)
            dest.write_bytes(pdf_bytes)
            print(f"  -> OK ({len(pdf_bytes)} bytes)")
            succeeded += 1
        except ArchiveOrgError as exc:
            print(f"  -> FAILED: {exc}")
            failed += 1
        time.sleep(DELAY_BETWEEN_DOWNLOADS_SECONDS)

    print(f"\nDownloaded: {succeeded}, skipped (already present): {skipped}, failed: {failed}.")

    if do_ingest:
        print("\nRunning bulk ingest on the downloaded folder...\n")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.ingestion.bulk_ingest_cli",
                str(out_dir),
                "--document-type",
                "INDIAN_STANDARD",
                "--source",
                "internet_archive",
            ]
        )
        return result.returncode

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk-download real Indian Standards from Internet Archive.")
    parser.add_argument("output_folder", help="Folder to save downloaded PDFs into")
    parser.add_argument("--query", default=None, help="Keyword(s) to search for in standard titles, e.g. 'water heater'")
    parser.add_argument(
        "--identifiers-file",
        default=None,
        help="Path to a text file with one Internet Archive identifier per line (e.g. gov.in.is.10500.2012), instead of --query",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max results to download when using --query (default 50)")
    parser.add_argument("--ingest", action="store_true", help="Also run bulk_ingest_cli on the folder after downloading")
    args = parser.parse_args()

    identifiers = None
    if args.identifiers_file:
        identifiers = [line.strip() for line in Path(args.identifiers_file).read_text().splitlines() if line.strip()]

    sys.exit(run(args.output_folder, args.query, identifiers, args.limit, args.ingest))

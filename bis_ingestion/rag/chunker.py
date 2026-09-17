"""
rag/chunker.py — RAG chunker for BIS Standards records.

Converts BISStandard records into RAGChunk objects ready for embedding
into a vector store.

Chunking strategy:
  1. Each distinct metadata field (scope, title, status line) becomes
     its own chunk — short, focused, highly relevant to specific queries.
  2. If a scope/description is long, it is split into overlapping token-
     approximate windows (RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP from config).
  3. Every chunk carries full provenance (standard_number, source_url)
     so that citations are always traceable to the official BIS page.

Token counting:
  - Uses a simple whitespace-based approximation (words ≈ tokens * 0.75).
  - Replace with tiktoken or sentencepiece if exact counts are needed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from bis_ingestion.config import (
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_CHUNKS_JSONL_PATH,
)
from bis_ingestion.schemas import BISStandard, RAGChunk

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token approximation
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    """Approximate token count: words / 0.75 (rough GPT-style ratio)."""
    return int(len(text.split()) / 0.75)


# ---------------------------------------------------------------------------
# Text windowing
# ---------------------------------------------------------------------------

def _split_text(
    text: str,
    chunk_size: int = RAG_CHUNK_SIZE,
    overlap: int = RAG_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split a long text into overlapping token-approximate windows.

    Args:
        text: Input text to split
        chunk_size: Target max tokens per chunk
        overlap: Overlap in tokens between consecutive chunks

    Returns:
        List of text chunks
    """
    words = text.split()
    if not words:
        return []

    # Convert token targets to word counts (approx)
    words_per_chunk = int(chunk_size * 0.75)
    words_overlap = int(overlap * 0.75)

    if len(words) <= words_per_chunk:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + words_per_chunk, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - words_overlap
        if start < 0:
            start = 0

    return chunks


# ---------------------------------------------------------------------------
# Core chunking function
# ---------------------------------------------------------------------------

def _build_header(std: BISStandard) -> str:
    """Build a short metadata header prepended to every chunk."""
    parts = [std.standard_number]
    if std.title:
        parts.append(std.title)
    if std.status:
        parts.append(f"[{std.status}]")
    if std.edition_year:
        parts.append(f"Edition: {std.edition_year}")
    return " | ".join(parts)


def chunk_standard(std: BISStandard) -> list[RAGChunk]:
    """
    Decompose a single BISStandard into a list of RAGChunks.

    Each logical section (scope, status, amendments, etc.) becomes
    its own chunk. Long sections are further windowed.
    """
    chunks: list[RAGChunk] = []
    header = _build_header(std)

    def _add(clause: str, text: str) -> None:
        """Helper: add one or more chunks for a given clause/text."""
        if not text or not text.strip():
            return
        full_text = f"{header}\n\n{clause}:\n{text.strip()}"
        windows = _split_text(full_text)
        for window in windows:
            chunks.append(
                RAGChunk(
                    standard_number=std.standard_number,
                    title=std.title,
                    part=std.part,
                    edition=std.edition_year,
                    clause=clause,
                    text=window,
                    status=std.status,
                    source_url=std.source_url,
                    token_count=_approx_tokens(window),
                )
            )

    # --- Identity / header chunk ---
    identity_parts = [f"Standard: {std.standard_number}"]
    if std.title:
        identity_parts.append(f"Title: {std.title}")
    if std.status:
        identity_parts.append(f"Status: {std.status}")
    if std.edition_year:
        identity_parts.append(f"Year: {std.edition_year}")
    if std.ics_code:
        identity_parts.append(f"ICS: {std.ics_code}")
    if std.technical_committee:
        identity_parts.append(f"Technical Committee: {std.technical_committee}")
    if std.department:
        identity_parts.append(f"Department: {std.department}")
    if std.certification_scheme:
        identity_parts.append(f"Certification Scheme: {std.certification_scheme}")
    if std.has_mandatory_certification is not None:
        cert_text = "Yes" if std.has_mandatory_certification else "No"
        identity_parts.append(f"Mandatory Certification: {cert_text}")

    _add("Metadata", "\n".join(identity_parts))

    # --- Scope ---
    if std.scope:
        _add("Scope", std.scope)

    # --- Amendments ---
    if std.amendments:
        amd_lines = []
        for a in std.amendments:
            num = a.get("number", "?")
            year = a.get("year", "")
            title = a.get("title", "")
            amd_lines.append(f"Amendment {num} ({year}): {title}".strip(": "))
        _add("Amendments", "\n".join(amd_lines))

    # --- Supersession ---
    sup_parts = []
    if std.supersedes:
        sup_parts.append(f"Supersedes: {std.supersedes}")
    if std.superseded_by:
        sup_parts.append(f"Superseded by: {std.superseded_by}")
    if std.related_standards:
        sup_parts.append(f"Related Standards: {', '.join(std.related_standards)}")
    if sup_parts:
        _add("Relationships", "\n".join(sup_parts))

    # --- Lab information ---
    if std.labs:
        lab_lines = []
        for lab in std.labs:
            lab_name = lab.get("lab_name", "")
            product = lab.get("product", "")
            charges = lab.get("testing_charges", "")
            lab_lines.append(f"Lab: {lab_name} | Product: {product} | Charges: {charges}")
        _add("Testing Labs", "\n".join(lab_lines))

    # --- Testing information ---
    if std.testing_information:
        _add("Testing Information", std.testing_information)

    return chunks


def chunk_standards_list(standards: list[BISStandard]) -> list[RAGChunk]:
    """Chunk all records in a list and return the combined list of RAGChunks."""
    all_chunks: list[RAGChunk] = []
    for std in standards:
        chunks = chunk_standard(std)
        all_chunks.extend(chunks)
    logger.info("Generated %d RAG chunks from %d standards", len(all_chunks), len(standards))
    return all_chunks


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------

def write_chunks_to_jsonl(
    chunks: list[RAGChunk],
    output_path: Path = RAG_CHUNKS_JSONL_PATH,
) -> Path:
    """
    Write RAGChunk records to a JSONL file.

    Args:
        chunks: List of RAGChunk objects
        output_path: Destination .jsonl file path

    Returns:
        Path to the written file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(_json.dumps(chunk.model_dump(), ensure_ascii=False))
            f.write("\n")
    logger.info("Wrote %d RAG chunks to %s", len(chunks), output_path)
    return output_path


def iter_chunks_from_jsonl(path: Path) -> Iterator[RAGChunk]:
    """Lazily read RAGChunk records from a JSONL file."""
    import json as _json
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield RAGChunk(**_json.loads(line))


def stream_chunks_from_standards(
    standards: list[BISStandard],
    output_path: Path = RAG_CHUNKS_JSONL_PATH,
) -> int:
    """
    Chunk all standards and write to JSONL in a single streaming pass.
    More memory-efficient than chunk_standards_list() for large datasets.

    Returns:
        Total number of chunks written
    """
    import json as _json
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for std in standards:
            for chunk in chunk_standard(std):
                f.write(_json.dumps(chunk.model_dump(), ensure_ascii=False))
                f.write("\n")
                total += 1
    logger.info("Streamed %d RAG chunks to %s", total, output_path)
    return total

"""
Chunking strategy — Phase 4 baseline.

CHOSEN STRATEGY (documented, not claimed optimal — see docs/RAG_RETRIEVAL.md):
  1. Never cross a page boundary. Every chunk belongs to exactly one
     DocumentPage, so page-number provenance is always exact, never
     ambiguous ("this chunk spans pages 4-5").
  2. Within a page, split on section headings first (reusing
     app/ingestion/feature_extraction.py's SECTION_HEADING_PATTERN — the
     same pattern that already detects clause headings for feature
     extraction, so chunk boundaries and detected sections agree with each
     other by construction, not by coincidence).
  3. Within a section (or the whole page if no headings were found), split
     on paragraph boundaries (blank lines), then greedily pack paragraphs
     into chunks up to TARGET_CHUNK_CHARS, backtracking by
     CHUNK_OVERLAP_CHARS of trailing text when a chunk is closed, so
     adjacent chunks share context rather than cutting a sentence in half
     at an arbitrary character offset.
  4. A single paragraph longer than TARGET_CHUNK_CHARS is NOT split
     mid-paragraph in this baseline — it becomes its own (oversized) chunk
     rather than being cut at a character boundary that might land inside
     a technical term or clause number. This is a deliberate simplicity
     trade-off, not an oversight — see docs/RAG_RETRIEVAL.md §"Limitations".

TARGET_CHUNK_CHARS = 800, CHUNK_OVERLAP_CHARS = 100: chosen because BIS-style
clause text (short, dense technical sentences) tends to fit 2-4 clauses in
~800 characters — enough context for a retrieval match to be meaningful
without pulling in unrelated clauses. These are baseline values for the
initial retrieval system, not benchmarked against real BIS documents (none
were available — see docs/IMPLEMENTATION_ROADMAP.md Phase 3/4).

DETERMINISM: chunking has no randomness and no dependency on anything
outside its own text input — the same DocumentPage.text always produces
the same list of chunks, in the same order, verified by a dedicated test.
"""

from dataclasses import dataclass

from app.ingestion.feature_extraction import SECTION_HEADING_PATTERN

TARGET_CHUNK_CHARS = 800
CHUNK_OVERLAP_CHARS = 100


@dataclass
class Chunk:
    text: str
    section: str | None


def _split_into_sections(page_text: str) -> list[tuple[str | None, str]]:
    """Splits page text at section-heading boundaries. Returns a list of
    (section_id_or_None, section_text) in original order. If no heading is
    found, the whole page is one section with section=None."""
    matches = list(SECTION_HEADING_PATTERN.finditer(page_text))
    if not matches:
        return [(None, page_text)]

    sections: list[tuple[str | None, str]] = []
    # Text before the first heading (if any) has no section id.
    if matches[0].start() > 0:
        preamble = page_text[: matches[0].start()].strip()
        if preamble:
            sections.append((None, preamble))

    for i, match in enumerate(matches):
        section_id = match.group(1)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(page_text)
        sections.append((section_id, page_text[start:end].strip()))

    return sections


def _split_into_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n")]
    return [p for p in paragraphs if p]


def _pack_paragraphs(paragraphs: list[str]) -> list[str]:
    """Greedily packs paragraphs into chunks up to TARGET_CHUNK_CHARS, with
    CHUNK_OVERLAP_CHARS of trailing-text overlap carried into the next
    chunk. A single oversized paragraph becomes its own chunk unsplit."""
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= TARGET_CHUNK_CHARS or not current:
            current = candidate
            continue

        # Closing the current chunk; carry overlap into the next one.
        chunks.append(current)
        overlap_text = current[-CHUNK_OVERLAP_CHARS:] if len(current) > CHUNK_OVERLAP_CHARS else current
        current = f"{overlap_text}\n\n{paragraph}"

    if current:
        chunks.append(current)

    return chunks


def chunk_page_text(page_text: str) -> list[Chunk]:
    """Deterministically splits one page's text into retrieval-sized
    chunks, preserving section provenance per chunk. Returns [] for
    empty/whitespace-only input rather than a single empty chunk."""
    if not page_text or not page_text.strip():
        return []

    chunks: list[Chunk] = []
    for section_id, section_text in _split_into_sections(page_text):
        paragraphs = _split_into_paragraphs(section_text)
        if not paragraphs:
            continue
        for packed_text in _pack_paragraphs(paragraphs):
            chunks.append(Chunk(text=packed_text, section=section_id))

    return chunks

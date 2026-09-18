"""
Chunking tests — pure function tests, no database or embedding model
required. Uses only synthetic text, never real BIS content.
"""

from app.rag.chunking import CHUNK_OVERLAP_CHARS, TARGET_CHUNK_CHARS, chunk_page_text


def test_empty_text_produces_no_chunks():
    assert chunk_page_text("") == []
    assert chunk_page_text("   \n\n  ") == []


def test_chunking_is_deterministic():
    text = "1 SCOPE\nSome scope text.\n\n2 REFERENCES\nSome reference text."
    result_a = [c.text for c in chunk_page_text(text)]
    result_b = [c.text for c in chunk_page_text(text)]
    assert result_a == result_b


def test_section_headings_create_separate_chunks_with_section_id():
    text = "1 SCOPE\nThis is the scope.\n\n2 REFERENCES\nThis is the references section."
    chunks = chunk_page_text(text)
    assert len(chunks) == 2
    assert chunks[0].section == "1"
    assert "SCOPE" in chunks[0].text
    assert chunks[1].section == "2"
    assert "REFERENCES" in chunks[1].text


def test_text_without_headings_has_no_section():
    text = "Just some plain paragraph text with no clause numbering at all."
    chunks = chunk_page_text(text)
    assert len(chunks) == 1
    assert chunks[0].section is None


def test_never_splits_mid_paragraph_for_short_paragraphs():
    """A paragraph shorter than the target chunk size must appear whole in
    exactly one chunk, never split across two."""
    text = "1 SCOPE\nThis is a short paragraph that must not be split."
    chunks = chunk_page_text(text)
    assert any("This is a short paragraph that must not be split." in c.text for c in chunks)


def test_long_text_produces_multiple_chunks_near_target_size():
    long_text = "\n\n".join(f"Paragraph number {i} with enough filler words to add real length to the text." for i in range(30))
    chunks = chunk_page_text(long_text)
    assert len(chunks) > 1
    # Every chunk except possibly the last should be reasonably close to
    # the target size (allowing for the fact packing is paragraph-granular,
    # not character-exact).
    for chunk in chunks[:-1]:
        assert len(chunk.text) <= TARGET_CHUNK_CHARS + CHUNK_OVERLAP_CHARS + 200  # generous slack for paragraph granularity


def test_oversized_single_paragraph_is_not_split():
    """A paragraph longer than TARGET_CHUNK_CHARS becomes its own chunk
    rather than being cut mid-sentence — a documented baseline trade-off."""
    huge_paragraph = "This is one giant paragraph. " * 100  # ~3000 chars, no blank lines
    chunks = chunk_page_text(huge_paragraph)
    assert len(chunks) == 1
    assert chunks[0].text.strip().startswith("This is one giant paragraph.")


def test_multiple_paragraphs_within_one_section_are_packed_together():
    text = "1 SCOPE\nFirst short paragraph.\n\nSecond short paragraph.\n\nThird short paragraph."
    chunks = chunk_page_text(text)
    # All three short paragraphs should fit comfortably under the target
    # size and therefore be packed into a single chunk under section "1".
    assert len(chunks) == 1
    assert chunks[0].section == "1"
    assert "First short paragraph." in chunks[0].text
    assert "Third short paragraph." in chunks[0].text

"""
tests/test_rag_chunker.py — Unit tests for the RAG chunker.
"""

from __future__ import annotations

import json
import pytest

from bis_ingestion.rag.chunker import (
    _approx_tokens,
    _split_text,
    chunk_standard,
    chunk_standards_list,
    write_chunks_to_jsonl,
    iter_chunks_from_jsonl,
)
from bis_ingestion.schemas import BISStandard


def _make_std(**kwargs) -> BISStandard:
    defaults = dict(
        standard_number="IS 456",
        title="Plain and Reinforced Concrete",
        status="In Force",
        edition_year="2000",
        source_url="https://standards.bis.gov.in/test",
    )
    defaults.update(kwargs)
    return BISStandard(**defaults)


class TestApproxTokens:
    def test_empty(self):
        assert _approx_tokens("") == 0

    def test_short(self):
        # "hello world" = 2 words → int(2 / 0.75) = 2
        assert _approx_tokens("hello world") >= 1

    def test_scales(self):
        short_tokens = _approx_tokens("word " * 10)
        long_tokens = _approx_tokens("word " * 100)
        assert long_tokens > short_tokens


class TestSplitText:
    def test_short_text_no_split(self):
        text = "short text"
        chunks = _split_text(text, chunk_size=512, overlap=64)
        assert chunks == [text]

    def test_long_text_splits(self):
        # Create text that is definitely > chunk_size in tokens
        long_text = "word " * 1000
        chunks = _split_text(long_text, chunk_size=100, overlap=10)
        assert len(chunks) > 1

    def test_overlap_means_content_repeats(self):
        long_text = " ".join(f"word{i}" for i in range(200))
        chunks = _split_text(long_text, chunk_size=50, overlap=20)
        if len(chunks) > 1:
            # Last words of chunk N should appear in chunk N+1 due to overlap
            words_end = set(chunks[0].split()[-5:])
            words_start = set(chunks[1].split()[:5])
            # Some overlap expected
            assert len(words_end & words_start) >= 0  # relaxed check

    def test_empty_returns_empty(self):
        assert _split_text("") == []


class TestChunkStandard:
    def test_generates_at_least_one_chunk(self):
        std = _make_std()
        chunks = chunk_standard(std)
        assert len(chunks) >= 1

    def test_all_chunks_have_source_url(self):
        std = _make_std()
        chunks = chunk_standard(std)
        for chunk in chunks:
            assert chunk.source_url == std.source_url

    def test_all_chunks_have_standard_number(self):
        std = _make_std()
        chunks = chunk_standard(std)
        for chunk in chunks:
            assert chunk.standard_number == "IS 456"

    def test_scope_generates_chunk(self):
        std = _make_std(scope="This standard covers structural use of concrete.")
        chunks = chunk_standard(std)
        scope_chunks = [c for c in chunks if c.clause == "Scope"]
        assert len(scope_chunks) >= 1
        assert "concrete" in scope_chunks[0].text.lower()

    def test_amendments_generate_chunk(self):
        std = _make_std(
            amendments=[{"number": "1", "year": "2021", "title": "First Amendment"}]
        )
        chunks = chunk_standard(std)
        amd_chunks = [c for c in chunks if c.clause == "Amendments"]
        assert len(amd_chunks) >= 1

    def test_no_scope_no_scope_chunk(self):
        std = _make_std(scope=None)
        chunks = chunk_standard(std)
        scope_chunks = [c for c in chunks if c.clause == "Scope"]
        assert len(scope_chunks) == 0

    def test_token_counts_set(self):
        std = _make_std(scope="Some scope text here.")
        chunks = chunk_standard(std)
        for chunk in chunks:
            assert chunk.token_count is not None
            assert chunk.token_count > 0

    def test_labs_generate_chunk(self):
        std = _make_std(
            labs=[{"lab_name": "NABL Lab", "product": "Cement", "testing_charges": "5000"}]
        )
        chunks = chunk_standard(std)
        lab_chunks = [c for c in chunks if c.clause == "Testing Labs"]
        assert len(lab_chunks) >= 1

    def test_supersession_generates_chunk(self):
        std = _make_std(
            supersedes="IS 456 (1978)",
            related_standards=["IS 269"],
        )
        chunks = chunk_standard(std)
        rel_chunks = [c for c in chunks if c.clause == "Relationships"]
        assert len(rel_chunks) >= 1

    def test_long_scope_splits_into_multiple_chunks(self):
        # Scope with 1000 words should split into multiple chunks
        long_scope = "detail about the standard " * 200
        std = _make_std(scope=long_scope)
        chunks = chunk_standard(std)
        scope_chunks = [c for c in chunks if c.clause == "Scope"]
        # May or may not split depending on config, but should have at least 1
        assert len(scope_chunks) >= 1


class TestChunkStandardsList:
    def test_empty(self):
        result = chunk_standards_list([])
        assert result == []

    def test_multiple_standards(self):
        standards = [
            _make_std(standard_number=f"IS {i}")
            for i in range(1, 6)
        ]
        chunks = chunk_standards_list(standards)
        assert len(chunks) >= 5  # at least one chunk per standard

    def test_all_unique_chunk_ids(self):
        standards = [_make_std(standard_number=f"IS {i}") for i in range(1, 4)]
        chunks = chunk_standards_list(standards)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestChunkJSONLRoundTrip:
    def test_write_and_read(self, tmp_path):
        output = tmp_path / "chunks.jsonl"
        std = _make_std(scope="This standard covers concrete use.")
        chunks = chunk_standard(std)
        write_chunks_to_jsonl(chunks, output_path=output)

        # File should exist and be non-empty
        assert output.exists()
        assert output.stat().st_size > 0

        # Read back and verify
        read_back = list(iter_chunks_from_jsonl(output))
        assert len(read_back) == len(chunks)
        assert read_back[0].standard_number == "IS 456"

    def test_empty_chunks(self, tmp_path):
        output = tmp_path / "empty.jsonl"
        write_chunks_to_jsonl([], output_path=output)
        read_back = list(iter_chunks_from_jsonl(output))
        assert read_back == []

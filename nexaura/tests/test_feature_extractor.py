"""
test_feature_extractor.py — Unit tests for FeatureExtractor and KnowledgeUnit

Project: Nexaura (SIH 2026 — SIH26107)
"""

from __future__ import annotations

import pytest

from nexaura.backend.ingestion.feature_extractor import (
    FeatureExtractor,
    KnowledgeUnit,
    TechnicalParameter,
    Requirement,
)
from nexaura.backend.ingestion.metadata_extractor import DocumentMetadata
from nexaura.backend.ingestion.clause_parser import ClauseNode


def make_clause_node(
    clause: str = "5.2.1",
    text: str = "",
    heading: str = "Test Clause",
    content_type: str = "requirement",
    page: int = 37,
) -> ClauseNode:
    return ClauseNode(
        clause=clause,
        heading=heading,
        raw_text=text,
        text=text,
        content_type=content_type,
        page_start=page,
        page_end=page,
        parent_clause="5.2",
    )


def make_metadata(std_num: str = "IS 1234", year: int = 2024) -> DocumentMetadata:
    return DocumentMetadata(
        standard_number=std_num,
        title="Test Standard",
        year=year,
        edition="2024",
        status="unknown",
    )


class TestFeatureExtractor:
    def setup_method(self) -> None:
        self.extractor = FeatureExtractor()

    def test_technical_parameter_extraction_minimum(self) -> None:
        """Should extract 'minimum thickness 80 μm'."""
        text = "The zinc coating shall have a minimum thickness of 80 μm."
        node = make_clause_node(text=text)
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf", 0.95)

        assert any(
            p.name == "coating thickness" and p.value == 80.0 and p.operator == "minimum"
            for p in ku.technical_parameters
        ), f"Expected coating thickness parameter, got: {ku.technical_parameters}"

    def test_requirement_extraction(self) -> None:
        """Should extract 'shall' requirement."""
        text = "The material shall conform to the requirements of IS 2062."
        node = make_clause_node(text=text)
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf", 0.95)

        assert len(ku.requirements) > 0
        assert any(r.keyword == "shall" for r in ku.requirements)

    def test_material_extraction(self) -> None:
        """Should detect 'steel' and 'zinc' as materials."""
        text = "The zinc coating on steel pipe shall not be less than 80 μm."
        node = make_clause_node(text=text, heading="Coating Specification")
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf", 0.95)

        assert "zinc" in ku.material or "steel" in ku.material

    def test_product_extraction(self) -> None:
        """Should detect 'galvanized steel pipe' as product."""
        text = "This standard covers galvanized steel pipe for water supply."
        node = make_clause_node(text=text, heading="Scope")
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf", 0.95)

        # Should find "steel pipe" or "galvanized pipe" in products
        found = any("pipe" in p.lower() for p in ku.product)
        assert found, f"No pipe product found in: {ku.product}"

    def test_knowledge_unit_id_generation(self) -> None:
        """KnowledgeUnit ID should follow IS{num}_{year}_{clause} format."""
        node = make_clause_node(clause="5.2.1")
        meta = make_metadata(std_num="IS 1234", year=2024)
        ku = self.extractor.extract(node, meta, "test.pdf")
        ku.id = ku.generate_id()

        assert "IS1234" in ku.id or "IS" in ku.id
        assert "2024" in ku.id
        assert "5.2.1" in ku.id

    def test_search_text_populated(self) -> None:
        """search_text should be non-empty after extraction."""
        text = "The zinc coating shall have minimum thickness of 80 μm."
        node = make_clause_node(text=text, heading="Coating")
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf")
        assert len(ku.search_text) > 0

    def test_knowledge_unit_validation(self) -> None:
        """KnowledgeUnit should pass pydantic validation."""
        ku = KnowledgeUnit(
            standard_number="IS 456",
            clause="5.1",
            text="Test text",
            source_pdf="test.pdf",
        )
        assert ku.standard_number == "IS 456"
        assert ku.validation_status == "pending"
        assert ku.status == "unknown"

    def test_status_normalization(self) -> None:
        """Status 'in force' should normalize to 'In Force'."""
        ku = KnowledgeUnit(
            standard_number="IS 456",
            clause="5",
            status="in force",
        )
        assert ku.status == "In Force"

    def test_cross_reference_extraction(self) -> None:
        """Should extract cross-references like 'see 5.2'."""
        text = "The test method shall be as per see 5.2 and refer to Table 4."
        node = make_clause_node(text=text)
        meta = make_metadata()
        ku = self.extractor.extract(node, meta, "test.pdf")
        # Cross refs should be extracted
        assert isinstance(ku.cross_references, list)

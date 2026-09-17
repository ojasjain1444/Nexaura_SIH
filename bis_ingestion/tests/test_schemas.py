"""
tests/test_schemas.py — Unit tests for BIS data schemas and validators.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bis_ingestion.schemas import BISLab, BISStandard, CrawlState, RAGChunk


class TestBISStandard:
    def test_minimal_valid(self):
        std = BISStandard(
            standard_number="IS 456",
            source_url="https://standards.bis.gov.in/test",
        )
        assert std.standard_number == "IS 456"
        assert std.id  # UUID assigned
        assert std.last_checked  # date assigned

    def test_normalise_standard_number(self):
        std = BISStandard(
            standard_number="  is 456  ",
            source_url="https://standards.bis.gov.in/test",
        )
        assert std.standard_number == "IS 456"

    def test_normalise_status_in_force(self):
        std = BISStandard(
            standard_number="IS 1",
            source_url="https://standards.bis.gov.in/test",
            status="current",
        )
        assert std.status == "In Force"

    def test_normalise_status_withdrawn(self):
        std = BISStandard(
            standard_number="IS 2",
            source_url="https://standards.bis.gov.in/test",
            status="withdrawn",
        )
        assert std.status == "Withdrawn"

    def test_normalise_status_unknown_passthrough(self):
        std = BISStandard(
            standard_number="IS 3",
            source_url="https://standards.bis.gov.in/test",
            status="SomeNewStatus",
        )
        assert std.status == "SomeNewStatus"

    def test_missing_source_url_raises(self):
        with pytest.raises(ValidationError):
            BISStandard(standard_number="IS 456")  # source_url required

    def test_missing_standard_number_raises(self):
        with pytest.raises(ValidationError):
            BISStandard(source_url="https://standards.bis.gov.in/test")

    def test_amendments_default_empty_list(self):
        std = BISStandard(
            standard_number="IS 1",
            source_url="https://standards.bis.gov.in/test",
        )
        assert std.amendments == []

    def test_full_record(self):
        std = BISStandard(
            standard_number="IS 456",
            title="Plain and Reinforced Concrete",
            status="In Force",
            edition_year="2000",
            scope="Covers structural use of concrete.",
            ics_code="91.080.40",
            technical_committee="CED 2",
            certification_scheme="Scheme II",
            has_mandatory_certification=True,
            amendments=[{"number": "1", "year": "2021", "title": "AMD 1"}],
            supersedes="IS 456 (1978)",
            related_standards=["IS 269", "IS 1489"],
            source_url="https://standards.bis.gov.in/website/know-your-standards?standardNumber=IS456",
            source_system="BIS_STANDARDS_PORTAL",
        )
        assert std.technical_committee == "CED 2"
        assert std.has_mandatory_certification is True
        assert len(std.amendments) == 1
        assert len(std.related_standards) == 2

    def test_serialisation_round_trip(self):
        std = BISStandard(
            standard_number="IS 100",
            source_url="https://standards.bis.gov.in/test",
            amendments=[{"number": "1", "year": "2020"}],
        )
        data = std.model_dump()
        restored = BISStandard(**data)
        assert restored.standard_number == std.standard_number
        assert restored.amendments == std.amendments


class TestBISLab:
    def test_minimal_valid(self):
        lab = BISLab(
            lab_name="Test Lab",
            is_number="IS 456",
            source_url="https://lims.bis.gov.in/home/search_is_number/",
        )
        assert lab.lab_name == "Test Lab"
        assert lab.id  # UUID assigned

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            BISLab(lab_name="Test Lab")  # is_number and source_url required


class TestRAGChunk:
    def test_minimal_valid(self):
        chunk = RAGChunk(
            standard_number="IS 456",
            text="This chunk covers the scope of IS 456.",
            source_url="https://standards.bis.gov.in/test",
        )
        assert chunk.chunk_id
        assert chunk.text == "This chunk covers the scope of IS 456."

    def test_missing_text_raises(self):
        with pytest.raises(ValidationError):
            RAGChunk(
                standard_number="IS 456",
                source_url="https://standards.bis.gov.in/test",
            )


class TestCrawlState:
    def test_defaults(self):
        state = CrawlState()
        assert state.total_records_collected == 0
        assert state.errors_count == 0
        assert state.sources_completed == []

    def test_update_fields(self):
        state = CrawlState(
            lims_last_is_no=100,
            total_records_collected=250,
        )
        assert state.lims_last_is_no == 100

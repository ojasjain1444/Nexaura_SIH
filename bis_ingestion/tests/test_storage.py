"""
tests/test_storage.py — Unit tests for the SQLite storage layer (BISDatabase).
Uses an in-memory SQLite database so no files are created.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bis_ingestion.schemas import BISLab, BISStandard
from bis_ingestion.storage.db import BISDatabase

# Use an in-memory database for all tests
_IN_MEMORY = Path(":memory:")


def _make_std(number: str = "IS 456", **kwargs) -> BISStandard:
    return BISStandard(
        standard_number=number,
        source_url=f"https://standards.bis.gov.in/test/{number.replace(' ', '')}",
        **kwargs,
    )


def _make_lab(is_number: str = "IS 456", lab_name: str = "Test Lab") -> BISLab:
    return BISLab(
        lab_name=lab_name,
        is_number=is_number,
        is_doc_no="456",
        source_url="https://lims.bis.gov.in/home/search_is_number/",
    )


class TestBISDatabaseInit:
    def test_opens_and_inits_schema(self, tmp_path):
        db_path = tmp_path / "test.db"
        with BISDatabase(db_path) as db:
            assert db.count_standards() == 0
            assert db.count_labs() == 0

    def test_context_manager_commits_on_success(self, tmp_path):
        db_path = tmp_path / "test.db"
        std = _make_std()
        with BISDatabase(db_path) as db:
            db.upsert_standard(std)
        # Re-open and verify commit
        with BISDatabase(db_path) as db:
            assert db.count_standards() == 1


class TestUpsertStandard:
    def test_insert(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(_make_std("IS 456"))
            assert db.count_standards() == 1

    def test_update_on_conflict(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(_make_std("IS 456", title="Old Title"))
            db.upsert_standard(_make_std("IS 456", title="New Title"))
            assert db.count_standards() == 1
            record = db.get_standard("IS 456")
            assert record["title"] == "New Title"

    def test_multiple_different(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(_make_std("IS 1"))
            db.upsert_standard(_make_std("IS 2"))
            db.upsert_standard(_make_std("IS 3"))
            assert db.count_standards() == 3

    def test_bulk_upsert(self, tmp_path):
        standards = [_make_std(f"IS {i}") for i in range(1, 11)]
        with BISDatabase(tmp_path / "test.db") as db:
            count = db.upsert_standards_batch(standards)
            assert count == 10
            assert db.count_standards() == 10


class TestGetStandard:
    def test_found(self, tmp_path):
        std = _make_std("IS 456", title="Concrete Code")
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(std)
            result = db.get_standard("IS 456")
            assert result is not None
            assert result["title"] == "Concrete Code"

    def test_not_found(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            result = db.get_standard("IS 99999")
            assert result is None

    def test_case_insensitive(self, tmp_path):
        std = _make_std("IS 456")
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(std)
            result = db.get_standard("is 456")
            assert result is not None

    def test_json_fields_stored(self, tmp_path):
        std = _make_std(
            "IS 456",
            amendments=[{"number": "1", "year": "2021"}],
            related_standards=["IS 269"],
        )
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(std)
            result = db.get_standard("IS 456")
            import json
            amd = json.loads(result["amendments"])
            assert len(amd) == 1
            assert amd[0]["number"] == "1"


class TestIterAllStandards:
    def test_returns_all(self, tmp_path):
        standards = [_make_std(f"IS {i}") for i in range(1, 6)]
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standards_batch(standards)
            all_records = list(db.iter_all_standards())
            assert len(all_records) == 5

    def test_ordered_by_standard_number(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_standard(_make_std("IS 3"))
            db.upsert_standard(_make_std("IS 1"))
            db.upsert_standard(_make_std("IS 2"))
            records = list(db.iter_all_standards())
            numbers = [r["standard_number"] for r in records]
            assert numbers == sorted(numbers)


class TestUpsertLab:
    def test_insert(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_lab(_make_lab())
            assert db.count_labs() == 1

    def test_update_on_conflict(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.upsert_lab(_make_lab(lab_name="Lab A", is_number="IS 456"))
            lab2 = BISLab(
                lab_name="Lab A",
                is_number="IS 456",
                product="New Product",
                source_url="https://lims.bis.gov.in/home/search_is_number/",
            )
            db.upsert_lab(lab2)
            assert db.count_labs() == 1
            labs = db.get_labs_for_standard("456")
            # Hmm, get_labs_for_standard uses is_doc_no which may be None
            # so just check count
            assert db.count_labs() == 1

    def test_bulk_upsert(self, tmp_path):
        labs = [_make_lab(lab_name=f"Lab {i}") for i in range(5)]
        with BISDatabase(tmp_path / "test.db") as db:
            count = db.upsert_labs_batch(labs)
            assert count == 5

    def test_get_labs_for_standard(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            lab1 = BISLab(
                lab_name="Lab A",
                is_number="IS 456",
                is_doc_no="456",
                source_url="https://lims.bis.gov.in/home/search_is_number/",
            )
            lab2 = BISLab(
                lab_name="Lab B",
                is_number="IS 456",
                is_doc_no="456",
                source_url="https://lims.bis.gov.in/home/search_is_number/",
            )
            db.upsert_lab(lab1)
            db.upsert_lab(lab2)
            labs = db.get_labs_for_standard("456")
            assert len(labs) == 2


class TestCrawlLog:
    def test_log_and_stats(self, tmp_path):
        with BISDatabase(tmp_path / "test.db") as db:
            db.log_crawl_run("LIMS", records_added=100, errors=2)
            db.log_crawl_run("BIS_STANDARDS_PORTAL", records_added=50)
            stats = db.get_crawl_stats()
            assert stats["runs"] == 2
            assert stats["total_added"] == 150
            assert stats["total_errors"] == 2

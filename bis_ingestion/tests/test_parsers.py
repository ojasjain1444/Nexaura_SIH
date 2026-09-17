"""
tests/test_parsers.py — Unit tests for text_utils parser helpers.
"""

from __future__ import annotations

import pytest

from bis_ingestion.parsers import (
    clean_text,
    extract_amendment_numbers,
    extract_ics_codes,
    extract_is_numbers,
    extract_year,
    normalise_date,
    normalise_is_number,
    normalise_status,
    parse_is_components,
    slugify,
    strip_html_tags,
)


class TestNormaliseIsNumber:
    def test_basic(self):
        assert normalise_is_number("is 456") == "IS 456"

    def test_already_normalised(self):
        assert normalise_is_number("IS 456") == "IS 456"

    def test_extra_spaces(self):
        assert normalise_is_number("  IS   456  ") == "IS 456"

    def test_with_part(self):
        assert normalise_is_number("IS 1239 Part 1") == "IS 1239 PART 1"


class TestExtractIsNumbers:
    def test_single(self):
        result = extract_is_numbers("Please refer to IS 456 for details.")
        assert "IS 456" in result

    def test_multiple(self):
        result = extract_is_numbers("Both IS 269 and IS 456 apply.")
        assert len(result) >= 2
        assert "IS 269" in result
        assert "IS 456" in result

    def test_with_part(self):
        result = extract_is_numbers("IS 1239 Part 1 covers this.")
        assert any("1239" in r for r in result)

    def test_no_match(self):
        result = extract_is_numbers("No standard mentioned here.")
        assert result == []

    def test_deduplication(self):
        result = extract_is_numbers("IS 456 and IS 456 again.")
        assert result.count("IS 456") == 1


class TestParseIsComponents:
    def test_basic(self):
        result = parse_is_components("IS 456")
        assert result["doc_no"] == "456"
        assert result["part"] is None
        assert result["section"] is None
        assert result["year"] is None

    def test_with_year(self):
        result = parse_is_components("IS 1 (1968)")
        assert result["doc_no"] == "1"
        assert result["year"] == "1968"

    def test_with_part(self):
        result = parse_is_components("IS 1239 Part 1")
        assert result["doc_no"] == "1239"
        assert result["part"] == "1"

    def test_no_match(self):
        result = parse_is_components("not a standard")
        assert all(v is None for v in result.values())


class TestExtractYear:
    def test_found(self):
        assert extract_year("Published in 2022") == "2022"

    def test_not_found(self):
        assert extract_year("No year here") is None

    def test_takes_first(self):
        assert extract_year("2019 and 2020") == "2019"


class TestNormaliseDate:
    def test_none(self):
        assert normalise_date(None) is None

    def test_empty(self):
        assert normalise_date("") is None

    def test_dd_mm_yyyy(self):
        result = normalise_date("15/03/2022")
        assert result == "2022-03-15"

    def test_passthrough_if_no_match(self):
        result = normalise_date("March 2022")
        assert result == "March 2022"


class TestCleanText:
    def test_strips_whitespace(self):
        assert clean_text("  hello world  ") == "hello world"

    def test_collapses_newlines(self):
        assert clean_text("hello\n\nworld") == "hello world"

    def test_none_input(self):
        assert clean_text(None) is None

    def test_empty_string(self):
        assert clean_text("") is None

    def test_truncation(self):
        text = "a" * 100
        assert len(clean_text(text, max_len=50)) == 50


class TestSlugify:
    def test_basic(self):
        assert slugify("IS 456") == "is-456"

    def test_with_special_chars(self):
        assert slugify("IS 456 (Part 1)") == "is-456-part-1"


class TestExtractAmendmentNumbers:
    def test_amd(self):
        result = extract_amendment_numbers("AMD 1, AMD 2")
        assert result == ["1", "2"]

    def test_amendment_word(self):
        result = extract_amendment_numbers("Amendment 3 applies")
        assert "3" in result

    def test_none(self):
        result = extract_amendment_numbers("No amendments here")
        assert result == []


class TestExtractIcsCodes:
    def test_basic(self):
        result = extract_ics_codes("ICS: 91.080.30")
        assert "91.080.30" in result

    def test_multiple(self):
        result = extract_ics_codes("91.080.30 and 01.040.91")
        assert len(result) >= 2


class TestStripHtmlTags:
    def test_removes_tags(self):
        assert strip_html_tags("<b>Hello</b> World") == " Hello  World"

    def test_no_tags(self):
        assert strip_html_tags("plain text") == "plain text"


class TestNormaliseStatus:
    def test_in_force(self):
        assert normalise_status("in force") == "In Force"
        assert normalise_status("current") == "In Force"
        assert normalise_status("active") == "In Force"

    def test_withdrawn(self):
        assert normalise_status("withdrawn") == "Withdrawn"
        assert normalise_status("cancelled") == "Withdrawn"

    def test_under_revision(self):
        assert normalise_status("under revision") == "Under Revision"

    def test_passthrough(self):
        assert normalise_status("CustomStatus") == "CustomStatus"

    def test_none(self):
        assert normalise_status(None) is None

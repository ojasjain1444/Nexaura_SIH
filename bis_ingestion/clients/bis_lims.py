"""
bis_lims.py — Scraper for BIS LIMS (Laboratory Information Management System).

Source: https://lims.bis.gov.in/home/search_is_number/
Data: Publicly accessible HTML table of BIS-recognized labs and their testing scope.

The LIMS portal provides:
  - Lab name, OSL code
  - IS number, part, section, year
  - Product description
  - Testing charges
  - Validity dates

This is a Django server-rendered HTML application — no JavaScript required.
The search endpoint uses GET parameters and returns paginated HTML tables.

robots.txt: No restrictions declared (endpoint returns 404 HTML — treated as allow all).
"""

from __future__ import annotations

import logging
import re
from typing import Iterator, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from bis_ingestion.config import (
    LIMS_IS_END,
    LIMS_IS_START,
    LIMS_PAGE_SIZE,
    SOURCES,
    TEST_CRAWL_LIMIT,
)
from bis_ingestion.schemas import BISLab

logger = logging.getLogger(__name__)

BASE_URL = SOURCES["lims"]["base_url"]
SEARCH_URL = SOURCES["lims"]["lab_search_url"]


def _build_search_url(
    is_doc_no: str = "",
    is_part: str = "",
    is_section: str = "",
    is_year: str = "",
    is_title: str = "",
    lab_name: str = "",
    page: int = 1,
) -> str:
    """Build the LIMS search URL for a given IS number."""
    params: dict[str, str] = {}
    if is_doc_no:
        params["is_number__doc_no"] = is_doc_no
    if is_part:
        params["is_number__part"] = is_part
    if is_section:
        params["is_number__section"] = is_section
    if is_year:
        params["is_number__year"] = is_year
    if is_title:
        params["is_title"] = is_title
    if lab_name:
        params["lab__lab_name__icontains"] = lab_name
    if page > 1:
        params["page"] = str(page)
    return f"{SEARCH_URL}?{urlencode(params)}" if params else SEARCH_URL


def _parse_lims_table(html: str, source_url: str) -> list[BISLab]:
    """Parse the LIMS result HTML table into a list of BISLab records."""
    soup = BeautifulSoup(html, "lxml")
    records: list[BISLab] = []

    table = soup.find("table", id="dataTable")
    if not table:
        # Try alternate table selector
        table = soup.find("table", class_="customTable")
    if not table:
        logger.debug("No data table found in response")
        return records

    tbody = table.find("tbody")
    if not tbody:
        return records

    rows = tbody.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 6:
            continue

        # Extract cell text — strip whitespace
        def cell(i: int) -> str:
            return cells[i].get_text(separator=" ", strip=True) if i < len(cells) else ""

        # Column order (from observed HTML): S.No, Lab Name, OSL Code,
        # IS Standard No, Product, Grade/Type/Size, Testing Charges, Validity Date, Remark
        sno = cell(0)
        if not sno or not sno.strip().isdigit():
            continue  # Skip header-like rows

        is_number_raw = cell(3)
        if not is_number_raw:
            continue

        # Parse IS number components: "IS 1 (1968)" -> doc_no=1, year=1968
        is_match = re.match(
            r"IS\s*(\d+)\s*(?:Part\s*(\d+))?\s*(?:Sec(?:tion)?\s*(\d+))?\s*(?:\((\d{4})\))?",
            is_number_raw,
            re.IGNORECASE,
        )
        doc_no = is_match.group(1) if is_match else None
        part = is_match.group(2) if is_match else None
        section = is_match.group(3) if is_match else None
        year = is_match.group(4) if is_match else None

        lab = BISLab(
            lab_name=cell(1),
            osl_code=cell(2) or None,
            is_number=is_number_raw,
            is_doc_no=doc_no,
            is_part=part,
            is_section=section,
            is_year=year,
            product=cell(4) or None,
            grade_type=cell(5) or None,
            testing_charges=cell(6) or None,
            validity_date=cell(7) or None,
            remark=cell(8) if len(cells) > 8 else None,
            source_url=source_url,
        )
        records.append(lab)

    return records


def _get_total_count(soup: BeautifulSoup) -> Optional[int]:
    """Try to read the result count shown on the LIMS page."""
    count_div = soup.find(class_="counts")
    if count_div:
        text = count_div.get_text(strip=True)
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def crawl_lims_by_is_number(
    http_client,
    is_doc_no: int,
    limit: Optional[int] = None,
) -> list[BISLab]:
    """
    Collect all lab records for a specific IS document number.
    Handles pagination automatically.

    Args:
        http_client: BISHTTPClient instance
        is_doc_no: The numeric IS document number (e.g. 1 for "IS 1")
        limit: Optional max records to return

    Returns:
        List of BISLab records
    """
    all_records: list[BISLab] = []
    page = 1

    while True:
        url = _build_search_url(is_doc_no=str(is_doc_no), page=page)
        try:
            response = http_client.get(url)
        except Exception as e:
            logger.warning("Failed to fetch LIMS page for IS %s p%d: %s", is_doc_no, page, e)
            break

        soup = BeautifulSoup(response.text, "lxml")
        records = _parse_lims_table(response.text, source_url=url)

        if not records:
            logger.debug("No records on IS %s page %d — stopping pagination", is_doc_no, page)
            break

        all_records.extend(records)
        logger.info("IS %s page %d: %d records (total=%d)", is_doc_no, page, len(records), len(all_records))

        if limit and len(all_records) >= limit:
            all_records = all_records[:limit]
            break

        # Check if there are more pages (look for pagination links with "Next" or page numbers)
        pagination = soup.find("ul", class_="pagination")
        if not pagination:
            # No pagination widget — only one page of results
            break

        next_link = pagination.find("a", string=re.compile(r"Next|»", re.IGNORECASE))
        if not next_link:
            break  # No next page

        page += 1

    return all_records


def crawl_lims_range(
    http_client,
    is_start: int = LIMS_IS_START,
    is_end: int = LIMS_IS_END,
    limit: Optional[int] = None,
) -> Iterator[BISLab]:
    """
    Iterate through IS numbers from is_start to is_end,
    yielding BISLab records one at a time.

    This is the main entry point for a full LIMS crawl.
    Use limit=50 for the initial test crawl.
    """
    collected = 0
    for is_no in range(is_start, is_end + 1):
        records = crawl_lims_by_is_number(http_client, is_doc_no=is_no)
        for rec in records:
            yield rec
            collected += 1
            if limit and collected >= limit:
                logger.info("LIMS crawl reached limit=%d", limit)
                return

        if not records:
            logger.debug("IS %d: no records in LIMS, skipping", is_no)


def crawl_lims_search(
    http_client,
    query: str = "",
    lab_name: str = "",
    limit: Optional[int] = TEST_CRAWL_LIMIT,
) -> list[BISLab]:
    """
    Broad LIMS search by product keyword or lab name.
    Returns up to `limit` records.
    """
    all_records: list[BISLab] = []
    page = 1

    while True:
        url = _build_search_url(is_title=query, lab_name=lab_name, page=page)
        try:
            response = http_client.get(url)
        except Exception as e:
            logger.error("LIMS search failed: %s", e)
            break

        records = _parse_lims_table(response.text, source_url=url)
        if not records:
            break

        all_records.extend(records)
        logger.info("LIMS search page %d: %d records", page, len(records))

        if limit and len(all_records) >= limit:
            all_records = all_records[:limit]
            break

        soup = BeautifulSoup(response.text, "lxml")
        pagination = soup.find("ul", class_="pagination")
        if not pagination:
            break
        next_link = pagination.find("a", string=re.compile(r"Next|»", re.IGNORECASE))
        if not next_link:
            break

        page += 1

    return all_records

"""
bis_standards.py — Client for the BIS Standards Portal (standards.bis.gov.in).

Source: https://standards.bis.gov.in/website/know-your-standards
REST API: https://standardsadmin.bis.gov.in/review-service

This module communicates directly with the official BIS Standards Portal backend
REST API endpoints (POST /searchKnowStandards, /getSummaryDetails) using httpx.
Playwright and heavy browser automation are completely avoided, enabling fast,
reliable metadata extraction across all platforms (including Python 3.14).

Data collected (publicly visible metadata only):
  - Standard number, title, status, edition/year
  - Scope, ICS classification
  - Technical committee, department
  - Amendment list
  - Supersedes / superseded-by relationships

NOTE: Full IS document PDFs are NOT collected — only publicly visible metadata.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
import httpx

from bis_ingestion.config import (
    HEADERS,
    REQUEST_DELAY_MIN,
    REQUEST_TIMEOUT,
    SOURCES,
    TEST_CRAWL_LIMIT,
)
from bis_ingestion.schemas import BISStandard

logger = logging.getLogger(__name__)

BASE_URL = SOURCES["standards_portal"]["base_url"]
SEARCH_URL = SOURCES["standards_portal"]["search_url"]
API_BASE_URL = SOURCES["standards_portal"].get(
    "api_base_url", "https://standardsadmin.bis.gov.in/review-service"
)


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def _build_search_url(query: str, page: int = 1) -> str:
    """Build the standards portal search URL."""
    params = {"searchTerm": query}
    if page > 1:
        params["page"] = str(page)
    return f"{SEARCH_URL}?{urlencode(params)}"


def _build_detail_url(standard_number: str) -> str:
    """Build the detail page URL for a specific standard."""
    clean = standard_number.replace(" ", "").upper()
    return f"{BASE_URL}/website/know-your-standards?standardNumber={quote(clean)}"


# ---------------------------------------------------------------------------
# HTML Parsing Fallback (for static HTML pages or local inspection)
# ---------------------------------------------------------------------------

def _parse_standard_from_html(html: str, source_url: str) -> Optional[BISStandard]:
    """
    Parse a KYS detail page HTML and extract standard metadata.
    Returns None if the page does not contain a recognizable standard record.
    """
    soup = BeautifulSoup(html, "lxml")

    # Standard Number
    std_number_el = (
        soup.find("h1", class_=re.compile(r"standard[_-]?number", re.I))
        or soup.find("h2", class_=re.compile(r"standard", re.I))
        or soup.find(attrs={"data-field": "standardNumber"})
    )

    if not std_number_el:
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(IS\s+\d+(?:\s+Part\s+\d+)?(?:\s+Sec(?:tion)?\s+\d+)?)\b", text, re.IGNORECASE)
        if not m:
            return None
        standard_number = m.group(1).strip().upper()
    else:
        standard_number = std_number_el.get_text(strip=True).upper()

    # Title
    title_el = (
        soup.find("h1", class_=re.compile(r"title", re.I))
        or soup.find(class_=re.compile(r"standard[_-]?title", re.I))
        or soup.find("h2")
    )
    title = title_el.get_text(strip=True) if title_el else None

    # Status
    status_el = soup.find(class_=re.compile(r"status|badge", re.I))
    status = status_el.get_text(strip=True) if status_el else None

    if not status:
        text = soup.get_text(" ", strip=True)
        for keyword in ["In Force", "Withdrawn", "Under Revision", "Superseded", "Reaffirmed"]:
            if keyword.lower() in text.lower():
                status = keyword
                break

    # Edition / Year
    edition_year = None
    text = soup.get_text(" ", strip=True)
    m = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m:
        edition_year = m.group(1)

    # Scope
    scope_el = soup.find(id=re.compile(r"scope", re.I)) or soup.find(class_=re.compile(r"scope", re.I))
    scope = scope_el.get_text(strip=True)[:2000] if scope_el else None

    # ICS Code
    ics_el = soup.find(string=re.compile(r"ICS", re.I))
    ics_code = None
    if ics_el and ics_el.parent:
        m = re.search(r"[\d.]+(?:;\s*[\d.]+)*", ics_el.parent.get_text())
        if m:
            ics_code = m.group(0)

    # Technical Committee
    tc_el = soup.find(string=re.compile(r"committee|technical", re.I))
    technical_committee = None
    if tc_el and tc_el.parent:
        tc_text = tc_el.parent.get_text(strip=True)
        m = re.search(r"[A-Z]{2,}\s*\d+", tc_text)
        if m:
            technical_committee = m.group(0)

    # Amendments
    amendments: list[dict[str, Any]] = []
    amd_section = soup.find(string=re.compile(r"amendment", re.I))
    if amd_section and amd_section.parent:
        parent = amd_section.parent.parent or amd_section.parent
        for amd_el in parent.find_all(string=re.compile(r"AMD\s*\d+|Amendment\s*\d+", re.I)):
            m = re.search(r"(\d+)", amd_el)
            if m:
                amendments.append({"number": m.group(1), "title": amd_el.strip()})

    # Supersedes
    supersedes = None
    sup_el = soup.find(string=re.compile(r"supersedes", re.I))
    if sup_el and sup_el.parent:
        m = re.search(r"IS\s*\d+", sup_el.parent.get_text(), re.IGNORECASE)
        if m:
            supersedes = m.group(0).upper()

    return BISStandard(
        standard_number=standard_number,
        title=title,
        edition_year=edition_year,
        status=status,
        scope=scope,
        ics_code=ics_code,
        technical_committee=technical_committee,
        amendments=amendments,
        supersedes=supersedes,
        source_url=source_url,
        source_system="BIS_STANDARDS_PORTAL",
    )


# ---------------------------------------------------------------------------
# Official BIS Review Service REST API Client
# ---------------------------------------------------------------------------

def search_standards_api(
    query: str,
    client: Optional[httpx.Client] = None,
) -> list[dict[str, Any]]:
    """
    Search official BIS standards using the backend REST API.
    Endpoint: POST https://standardsadmin.bis.gov.in/review-service/searchKnowStandards
    """
    url = f"{API_BASE_URL}/searchKnowStandards"
    payload = {"searchText": query.strip()}
    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://standards.bis.gov.in",
        "Referer": "https://standards.bis.gov.in/",
    }

    try:
        if client:
            resp = client.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        else:
            with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT) as c:
                resp = c.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data.get("data", []) or []
            elif isinstance(data, list):
                return data
    except Exception as e:
        logger.warning("Error calling searchKnowStandards for '%s': %s", query, e)

    return []


def fetch_standard_summary_api(
    standard_enc_id: str,
    client: Optional[httpx.Client] = None,
) -> dict[str, Any]:
    """
    Fetch comprehensive standard summary using encrypted standard ID.
    Endpoint: POST https://standardsadmin.bis.gov.in/review-service/getSummaryDetails
    """
    url = f"{API_BASE_URL}/getSummaryDetails"
    payload = {"standardId": standard_enc_id}
    headers = {
        **HEADERS,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://standards.bis.gov.in",
        "Referer": "https://standards.bis.gov.in/",
    }

    try:
        if client:
            resp = client.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        else:
            with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT) as c:
                resp = c.post(url, json=payload, headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data.get("data", {}) or data
    except Exception as e:
        logger.warning("Error calling getSummaryDetails for '%s': %s", standard_enc_id, e)

    return {}


def parse_api_standard(item: dict[str, Any], summary: Optional[dict[str, Any]] = None) -> BISStandard:
    """
    Convert official BIS REST API search item and optional summary into a BISStandard object.
    """
    summary = summary or {}

    raw_number = item.get("standardNumber") or summary.get("standardNumber") or ""
    # Standard number might look like "IS 456:2000" or "IS 456"
    std_num = raw_number.strip().upper()
    if ":" in std_num:
        std_num_base, year_part = std_num.split(":", 1)
    else:
        std_num_base, year_part = std_num, None

    title = item.get("standardName") or summary.get("standardTitle") or summary.get("title")

    # Status
    withdraw_status = item.get("withdrawStatus")
    if withdraw_status == 1:
        status = "WITHDRAWN"
    else:
        status = summary.get("status") or "IN FORCE"

    edition_year = year_part or item.get("editionYear") or summary.get("editionYear")
    if not edition_year:
        pub = item.get("publishedOn") or summary.get("publishedOn")
        if pub and len(pub) >= 4:
            edition_year = pub[:4]

    scope = summary.get("scope") or summary.get("standardScope") or None
    technical_committee = summary.get("committeeName") or summary.get("committeeId") or item.get("committeeId")
    department = summary.get("departmentName") or summary.get("departmentId") or item.get("departmentId")

    source_url = _build_detail_url(std_num)

    return BISStandard(
        standard_number=std_num,
        title=title,
        edition_year=str(edition_year) if edition_year else None,
        status=status,
        scope=scope,
        technical_committee=str(technical_committee) if technical_committee else None,
        department=str(department) if department else None,
        source_url=source_url,
        source_system="BIS_STANDARDS_PORTAL",
    )


def crawl_standards_api(
    queries: list[str],
    limit: int = TEST_CRAWL_LIMIT,
) -> list[BISStandard]:
    """
    Crawl standards across multiple search queries using the official REST API.
    Deduplicates by standard_number.
    """
    seen: set[str] = set()
    all_records: list[BISStandard] = []

    with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT) as client:
        for query in queries:
            if len(all_records) >= limit:
                break

            logger.info("Querying BIS Standards REST API for: '%s'", query)
            items = search_standards_api(query, client=client)

            for item in items:
                if len(all_records) >= limit:
                    break

                std_num = (item.get("standardNumber") or "").strip().upper()
                if not std_num or std_num in seen:
                    continue

                seen.add(std_num)
                enc_id = item.get("standardEncId")
                summary = {}
                if enc_id:
                    time.sleep(REQUEST_DELAY_MIN)
                    summary = fetch_standard_summary_api(enc_id, client=client)

                record = parse_api_standard(item, summary)
                all_records.append(record)
                logger.info("Collected standard via API: %s — %s", record.standard_number, record.title)

    logger.info("Total unique standards collected via API: %d", len(all_records))
    return all_records


def fetch_standard_metadata_simple(
    http_client: Any,
    standard_number: str,
) -> Optional[BISStandard]:
    """
    Lightweight fallback that uses the official REST API or HTML.
    """
    # 1. First try the search API
    items = search_standards_api(standard_number)
    if items:
        enc_id = items[0].get("standardEncId")
        summary = fetch_standard_summary_api(enc_id) if enc_id else {}
        return parse_api_standard(items[0], summary)

    # 2. Fallback to HTML lookup
    detail_url = _build_detail_url(standard_number)
    try:
        response = http_client.get(detail_url)
        return _parse_standard_from_html(response.text, source_url=detail_url)
    except Exception as e:
        logger.warning("HTTP fallback failed for %s: %s", standard_number, e)
        return None

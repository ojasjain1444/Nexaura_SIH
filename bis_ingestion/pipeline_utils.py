"""
pipeline_utils.py — Helper utilities for the BIS ingestion pipeline.

Includes:
    promote_labs_to_standards()  — Create BISStandard stubs from LIMS lab records
                                   so they appear in exports and RAG chunks.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from bis_ingestion.schemas import BISStandard
from bis_ingestion.storage.db import BISDatabase

logger = logging.getLogger(__name__)


def promote_labs_to_standards(db: BISDatabase) -> int:
    """
    For every unique IS number in bis_labs, create a BISStandard stub record
    in bis_standards (if one doesn't already exist) and attach the lab list.

    This bridges the gap between LIMS lab data and the standards export/RAG pipeline.

    Returns:
        Number of standard stubs created/updated
    """
    # Fetch all unique IS doc numbers from labs
    cur = db.conn.execute(
        """
        SELECT
            is_doc_no,
            is_number,
            is_part,
            is_section,
            is_year,
            source_url,
            GROUP_CONCAT(id) as lab_ids
        FROM bis_labs
        WHERE is_doc_no IS NOT NULL
        GROUP BY is_doc_no, is_part, is_section
        ORDER BY CAST(is_doc_no AS INTEGER)
        """
    )
    rows = cur.fetchall()
    logger.info("Found %d unique IS number groups in bis_labs", len(rows))

    count = 0
    for row in rows:
        row = dict(row)
        is_doc_no = row["is_doc_no"]
        is_number_raw = row["is_number"]  # e.g. "IS 21 (1992)"
        is_part = row["is_part"]
        is_year = row["is_year"]

        # Build canonical standard number
        std_num_parts = [f"IS {is_doc_no}"]
        if is_part:
            std_num_parts.append(f"Part {is_part}")
        standard_number = " ".join(std_num_parts).upper()

        # Check if a standards record already exists
        existing = db.get_standard(standard_number)
        if existing:
            # Just update the labs attachment
            labs_cur = db.conn.execute(
                "SELECT * FROM bis_labs WHERE is_doc_no = ?", (is_doc_no,)
            )
            lab_records = [dict(r) for r in labs_cur.fetchall()]

            db.conn.execute(
                "UPDATE bis_standards SET labs = ? WHERE standard_number = ?",
                (json.dumps(lab_records), standard_number),
            )
            count += 1
            continue

        # Fetch all labs for this IS number
        labs_cur = db.conn.execute(
            "SELECT * FROM bis_labs WHERE is_doc_no = ?", (is_doc_no,)
        )
        lab_records = [dict(r) for r in labs_cur.fetchall()]

        # Build the LIMS source URL
        source_url = (
            f"https://lims.bis.gov.in/home/search_is_number/"
            f"?is_number__doc_no={is_doc_no}"
        )
        if is_part:
            source_url += f"&is_number__part={is_part}"

        # Derive product info from labs for context
        products = list({
            lab["product"] for lab in lab_records
            if lab.get("product") and lab["product"].strip()
        })
        product_text = "; ".join(products[:5]) if products else None

        # Build scope text from lab info
        scope_parts = []
        if products:
            scope_parts.append(
                f"BIS-recognized laboratories test this standard for: {', '.join(products[:10])}."
            )
        if lab_records:
            scope_parts.append(
                f"Total {len(lab_records)} NABL/BIS-recognized labs are authorized "
                f"to test for {standard_number}."
            )
        scope = " ".join(scope_parts) if scope_parts else None

        std = BISStandard(
            standard_number=standard_number,
            doc_no=is_doc_no,
            part=is_part,
            section=row.get("is_section"),
            edition_year=is_year,
            title=product_text,   # best guess from lab product descriptions
            scope=scope,
            labs=[
                {
                    "lab_name": lab.get("lab_name", ""),
                    "osl_code": lab.get("osl_code", ""),
                    "product": lab.get("product", ""),
                    "grade_type": lab.get("grade_type", ""),
                    "testing_charges": lab.get("testing_charges", ""),
                    "validity_date": lab.get("validity_date", ""),
                    "state": lab.get("state", ""),
                }
                for lab in lab_records
            ],
            source_url=source_url,
            source_system="LIMS",
        )

        try:
            db.upsert_standard(std)
            count += 1
            logger.info(
                "Promoted IS %s → BISStandard stub (%d labs)",
                standard_number, len(lab_records),
            )
        except Exception as e:
            logger.warning("Failed to promote IS %s: %s", standard_number, e)

    db.conn.commit()
    logger.info("promote_labs_to_standards: created/updated %d standard stubs", count)
    return count

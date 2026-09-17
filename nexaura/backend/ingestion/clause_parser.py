"""
clause_parser.py — Phase 3b: Clause Hierarchy Builder

Project: Nexaura (SIH 2026 — SIH26107)

Builds the full IS standard clause tree from layout blocks.

IS standards use hierarchical clause numbering:
    5
    5.1
    5.2
    5.2.1
    5.2.1.1

This module:
    - Recognizes all IS clause numbering patterns
    - Builds parent-child relationships
    - Handles multi-page clauses (merges and tracks page_start/page_end)
    - Produces a flat list of ClauseNode objects suitable for
      feature_extractor.py and KnowledgeUnit creation

Design principle:
    Every ClauseNode is a self-contained, traceable unit.
    parent_clause is always set from the document — never inferred.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from nexaura.backend.ingestion.layout_parser import LayoutBlock, LayoutResult

logger = logging.getLogger(__name__)


# =============================================================================
# Clause Numbering Utilities
# =============================================================================

CLAUSE_RE = re.compile(
    r"^("
    r"\d+(?:\.\d+)*"          # numeric: 1, 1.1, 1.2.3, 1.2.3.4
    r"|[A-Z]-\d+(?:\.\d+)*"  # annex: A-1, B-2.1
    r"|[A-Z]\.\d+(?:\.\d+)*" # dot annex: A.1, B.2.1
    r"|SCOPE|FOREWORD|DEF|ANNEX"  # special sections
    r")$"
)


def get_parent_clause(clause: str) -> Optional[str]:
    """
    Determine the parent clause number.

    Examples:
        "5.2.1"   → "5.2"
        "5.2"     → "5"
        "5"       → None
        "A-1.2"   → "A-1"
        "SCOPE"   → None

    Args:
        clause: Clause number string

    Returns:
        Parent clause string, or None if this is a top-level clause.
    """
    if not clause or clause in ("SCOPE", "FOREWORD", "DEF", "ANNEX"):
        return None

    # Numeric dotted: split on last dot
    if re.match(r"^\d+(\.\d+)+$", clause):
        return clause.rsplit(".", 1)[0]

    # Top-level numeric
    if re.match(r"^\d+$", clause):
        return None

    # Annex style: A-1.2 → A-1
    m = re.match(r"^([A-Z]-\d+)(\.\d+)+$", clause)
    if m:
        return m.group(1)

    # Top-level annex: A-1 → None
    if re.match(r"^[A-Z]-\d+$", clause):
        return None

    # Dot annex: A.1.2 → A.1
    m = re.match(r"^([A-Z]\.\d+)(\.\d+)+$", clause)
    if m:
        return m.group(1)

    # Top-level dot annex: A.1 → None
    if re.match(r"^[A-Z]\.\d+$", clause):
        return None

    return None


def get_clause_depth(clause: str) -> int:
    """
    Return the depth of a clause in the hierarchy (0-indexed).

    Examples:
        "5"       → 0
        "5.1"     → 1
        "5.2.1"   → 2
        "5.2.1.1" → 3
    """
    if not clause or clause in ("SCOPE", "FOREWORD"):
        return 0
    if re.match(r"^\d+$", clause):
        return 0
    if re.match(r"^\d+(\.\d+)+$", clause):
        return len(clause.split(".")) - 1
    return 0


# =============================================================================
# ClauseNode — core data model
# =============================================================================

@dataclass
class ClauseNode:
    """
    A single clause or sub-clause in a BIS standard.

    Each ClauseNode becomes one KnowledgeUnit in the database.
    """

    # Identity
    clause: str                        # e.g. "5.2.1"
    sub_clause: Optional[str] = None   # same as clause for leaf nodes
    parent_clause: Optional[str] = None
    heading: Optional[str] = None

    # Content
    text: str = ""
    raw_text: str = ""                 # preserved verbatim from extraction

    # Structure
    section: Optional[str] = None     # top-level section name (e.g. "REQUIREMENTS")
    content_type: str = "clause"       # clause | requirement | definition | note | annex | scope
    annex: Optional[str] = None        # annex identifier if applicable
    depth: int = 0                     # hierarchy depth (0 = top level)

    # Pages
    page_start: int = 0
    page_end: int = 0
    source_pages: list[int] = field(default_factory=list)

    # Children (not stored in DB — used only during building)
    children: list["ClauseNode"] = field(default_factory=list, repr=False)


# =============================================================================
# Clause Parser
# =============================================================================

class ClauseParser:
    """
    Builds a hierarchical clause tree from layout blocks.

    Input:  LayoutResult (from layout_parser.py)
    Output: list[ClauseNode] — flat list with parent references

    Processing:
    1. Iterate layout blocks in order
    2. Detect clause start boundaries
    3. Accumulate text until next clause boundary
    4. Set parent_clause using IS numbering rules
    5. Track page_start / page_end across multi-page clauses
    """

    def parse(self, layout: LayoutResult) -> list[ClauseNode]:
        """
        Parse layout blocks into a list of ClauseNodes.

        Args:
            layout: LayoutResult from LayoutParser

        Returns:
            Flat list of ClauseNode objects with parent relationships set.
        """
        nodes: list[ClauseNode] = []
        current_node: Optional[ClauseNode] = None
        current_text_parts: list[str] = []
        current_pages: list[int] = []
        section_tracker: Optional[str] = None

        def flush_current() -> None:
            """Finalize the current node and add to nodes list."""
            nonlocal current_node, current_text_parts, current_pages
            if current_node is not None:
                full_text = "\n".join(current_text_parts).strip()
                current_node.raw_text = full_text
                current_node.text = full_text
                current_node.source_pages = sorted(set(current_pages))
                if current_pages:
                    current_node.page_start = min(current_pages)
                    current_node.page_end = max(current_pages)
                nodes.append(current_node)
            current_node = None
            current_text_parts = []
            current_pages = []

        for block in layout.blocks:
            if block.is_clause_start and block.clause_number:
                # Flush previous clause
                flush_current()

                clause_num = block.clause_number
                parent = get_parent_clause(clause_num)
                depth = get_clause_depth(clause_num)

                # Determine content type
                content_type = self._infer_content_type(
                    clause_num, block.heading_text or "", block.text
                )

                # Track section (top-level clauses become section names)
                if depth == 0 and clause_num not in ("SCOPE", "FOREWORD"):
                    section_tracker = block.heading_text or clause_num

                current_node = ClauseNode(
                    clause=clause_num,
                    sub_clause=clause_num if depth > 0 else None,
                    parent_clause=parent,
                    heading=block.heading_text,
                    section=section_tracker,
                    content_type=content_type,
                    depth=depth,
                    annex=clause_num if clause_num.startswith(("Annex", "ANNEX")) else None,
                )
                current_pages.append(block.page)

                # The block text may contain the clause heading + start of text
                text_without_header = self._strip_clause_header(
                    block.text, clause_num, block.heading_text
                )
                if text_without_header:
                    current_text_parts.append(text_without_header)

            else:
                # Continuation of current clause
                if current_node is not None:
                    current_pages.append(block.page)
                    if block.text.strip():
                        current_text_parts.append(block.text.strip())
                else:
                    # Text before first clause (e.g. cover page, preamble)
                    logger.debug("Pre-clause text block: %s", block.text[:80])

        # Flush final clause
        flush_current()

        # Post-process: set sub_clause for leaf nodes
        for node in nodes:
            if node.clause and "." in node.clause:
                node.sub_clause = node.clause

        logger.info(
            "Clause parsing complete: %s → %d clauses",
            layout.pdf_name, len(nodes),
        )
        for node in nodes[:5]:  # Log first 5
            logger.debug(
                "  [%s] parent=%s depth=%d heading=%s text_len=%d",
                node.clause, node.parent_clause, node.depth,
                node.heading, len(node.text),
            )

        return nodes

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _infer_content_type(
        self,
        clause_num: str,
        heading: str,
        text: str,
    ) -> str:
        """Infer content type from clause identifier and text."""
        clause_upper = clause_num.upper()
        heading_upper = heading.upper()
        text_lower = text.lower()

        if clause_upper in ("SCOPE",):
            return "scope"
        if clause_upper in ("FOREWORD",):
            return "foreword"
        if "DEF" in clause_upper or "DEFINITION" in heading_upper:
            return "definition"
        if "ANNEX" in clause_upper or clause_num.startswith(("A-", "B-", "C-")):
            return "annex"
        if "NOTE" in heading_upper:
            return "note"
        if any(kw in text_lower for kw in ("shall", "shall not", "must", "shall be")):
            return "requirement"
        if "TABLE" in heading_upper:
            return "table_ref"

        return "clause"

    def _strip_clause_header(
        self,
        text: str,
        clause_num: str,
        heading: Optional[str],
    ) -> str:
        """
        Remove the clause number and heading from the start of text.

        Example:
            Input:  "5.2.1 Chemical Composition\nThe zinc coating..."
            Output: "The zinc coating..."
        """
        if not text:
            return ""

        # Try to strip "5.2.1 Heading\n" from the start
        prefix_parts = [re.escape(clause_num)]
        if heading:
            prefix_parts.append(re.escape(heading))
        pattern = r"^" + r"\s+".join(prefix_parts) + r"\s*\n?"
        stripped = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
        return stripped.strip()

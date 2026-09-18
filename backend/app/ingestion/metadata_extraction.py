"""
BIS document metadata extraction (Step 4).

Every extractor here is pattern-based and conservative: if a pattern
doesn't match with reasonable confidence, the field is left as None rather
than guessed. This module has no access to an LLM and makes no
probabilistic judgment calls — it is regex-based structural extraction
only, which is honest about its limits (it will miss metadata in unusual
formats) rather than fabricating a plausible-looking answer.

Real BIS PDFs (confirmed across multiple genuine standards, not just
synthetic fixtures) commonly begin with a few pages of front matter before
the actual cover page: a "Disclosure to Promote the Right To Information"
notice (page 1) and sometimes a blank/copyright page, THEN the real cover
page with the standard number, an "Indian Standard" marker, and the title.
Metadata extraction therefore needs to look across the first several pages,
not just page 1 — see extract_metadata()'s `pages_text` parameter.
"""

import re
from dataclasses import dataclass

# Matches "IS 14625", "IS 302-1", "IS 302 : 2023", "IS/ISO 2859-1" etc. —
# the standard BIS numbering convention seen throughout this project's
# reference data (see backend/app/db/seed.py for real examples of the
# pattern this is meant to recognize).
STANDARD_NUMBER_PATTERN = re.compile(r"\bIS(?:/[A-Z]+)?\s*\d{2,6}(?:[\s\-:]\d+)?\b")

# "First Revision", "Second Revision", "Third Edition", etc.
EDITION_PATTERN = re.compile(
    r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+(Revision|Edition|Reprint)\b",
    re.IGNORECASE,
)

# BIS cover pages typically show a standalone 4-digit publication/reaffirmation
# year (e.g. "( Reaffirmed 2020 )", "2023"), separate from the edition/revision
# line. Restricted to a plausible BIS publication range (1950-2099) so an
# unrelated 4-digit number (e.g. a clause number or price) is not mistaken
# for a year — still conservative: no match means None, never a guess.
PUBLICATION_YEAR_PATTERN = re.compile(r"\b(19[5-9]\d|20\d\d)\b")

# The real cover page reliably marks its own title with a standalone
# "Indian Standard" line (confirmed across multiple real BIS PDFs); the
# title is the text between that marker and the parenthetical revision
# note or the ICS/copyright block that follows it.
_INDIAN_STANDARD_MARKER = re.compile(r"^Indian Standard$", re.IGNORECASE)
_TITLE_BLOCK_END = re.compile(
    r"^\(?\s*(First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+(Revision|Edition|Reprint)\s*\)?$"
    r"|^ICS\b|^©|^\d+(\.\d+)*\s+[A-Z]",
    re.IGNORECASE,
)


@dataclass
class ExtractedMetadata:
    standard_number: str | None
    title: str | None
    edition: str | None
    publication_year: str | None


def extract_standard_number(text: str) -> str | None:
    match = STANDARD_NUMBER_PATTERN.search(text)
    return match.group(0).strip() if match else None


def extract_edition(text: str) -> str | None:
    match = EDITION_PATTERN.search(text)
    return match.group(0).strip() if match else None


def extract_publication_year(text: str) -> str | None:
    """
    Conservative: skips any 4-digit year that is actually part of an
    "IS ####" standard-number token (e.g. the "2062" in "IS 2062 : 2011"
    falls within the plausible-year range and would otherwise be matched
    first) — confirmed against real BIS cover pages where the standard
    number precedes the true publication year on the same line/block.
    """
    excluded_spans = [m.span() for m in STANDARD_NUMBER_PATTERN.finditer(text)]
    for match in PUBLICATION_YEAR_PATTERN.finditer(text):
        if any(start <= match.start() < end for start, end in excluded_spans):
            continue
        return match.group(0)
    return None


def extract_title(pages_text: str) -> str | None:
    """
    Conservative heuristic: real BIS cover pages mark the title with a
    standalone "Indian Standard" line, followed by the title itself (one
    or two lines, in caps) and then a parenthetical revision/edition note
    or the ICS/copyright block. This is checked against `pages_text`
    (which may span multiple pages — see extract_metadata) rather than
    assuming the title is on page 1, since real BIS PDFs commonly place a
    "Disclosure to Promote the Right To Information" notice and sometimes
    a blank page before the actual cover page. Returns None rather than
    guessing if the marker line is not found.
    """
    lines = [line.strip() for line in pages_text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if not _INDIAN_STANDARD_MARKER.match(line):
            continue
        title_lines = []
        for candidate in lines[i + 1 : i + 6]:  # title spans at most a couple of lines
            if _TITLE_BLOCK_END.match(candidate):
                break
            title_lines.append(candidate)
        if title_lines:
            return " ".join(title_lines)
    return None


def extract_metadata(pages_text: str) -> ExtractedMetadata:
    """
    `pages_text` should be the concatenated text of the first several
    pages (not just page 1) — see module docstring for why real BIS PDFs
    require looking past page 1's front matter to find the real cover page.
    """
    return ExtractedMetadata(
        standard_number=extract_standard_number(pages_text),
        title=extract_title(pages_text),
        edition=extract_edition(pages_text),
        publication_year=extract_publication_year(pages_text),
    )

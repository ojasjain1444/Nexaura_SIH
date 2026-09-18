"""
Feature extraction (Step 5) — transforms raw page text into structured,
source-located facts.

Each extractor function takes one page's text and yields zero or more
ExtractedFeature results. A document that doesn't match a given extractor's
pattern simply contributes no rows for that feature_type — there is no
placeholder or default value. This is intentionally a small, pattern-based
set of extractors (standard numbers found anywhere in the body text, and
section/clause headings) rather than a general "understand the document"
system — that kind of open-ended extraction belongs to the RAG/LLM phase,
not here.
"""

import re
from dataclasses import dataclass

from app.ingestion.metadata_extraction import STANDARD_NUMBER_PATTERN

# Matches BIS-style clause/section headings, e.g. "4.2 Sampling" or
# "3 SCOPE" — a leading numeric clause identifier followed by a heading
# phrase, on its own line.
SECTION_HEADING_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z0-9 ,\-/&()]{2,80})$", re.MULTILINE)


@dataclass
class ExtractedFeature:
    feature_type: str
    value: str
    page_number: int
    section: str | None


def extract_standard_number_mentions(page_text: str, page_number: int) -> list[ExtractedFeature]:
    seen: set[str] = set()
    features = []
    for match in STANDARD_NUMBER_PATTERN.finditer(page_text):
        value = match.group(0).strip()
        if value in seen:
            continue
        seen.add(value)
        features.append(ExtractedFeature(feature_type="standard_number", value=value, page_number=page_number, section=None))
    return features


def extract_section_headings(page_text: str, page_number: int) -> list[ExtractedFeature]:
    features = []
    for match in SECTION_HEADING_PATTERN.finditer(page_text):
        clause_id, heading_text = match.group(1), match.group(2).strip()
        features.append(
            ExtractedFeature(
                feature_type="section_heading",
                value=f"{clause_id} {heading_text}",
                page_number=page_number,
                section=clause_id,
            )
        )
    return features


# The full set of extractors run against every page. Adding a new feature
# type means adding a function here — the pipeline loop below stays
# unchanged.
EXTRACTORS = [extract_standard_number_mentions, extract_section_headings]


def extract_features_from_page(page_text: str, page_number: int) -> list[ExtractedFeature]:
    features: list[ExtractedFeature] = []
    for extractor in EXTRACTORS:
        features.extend(extractor(page_text, page_number))
    return features

"""
DocumentType — Phase 12 controlled document taxonomy.

Classifies WHAT KIND of BIS material a StandardDocument is, independent
of whether its authenticity has been verified (that's source_type — see
app/models/standard_document.py's module docstring for the distinction).

A fixed enum, never an arbitrary LLM-generated string. Assigned only at
upload time as an explicit user selection (see
app/api/routes/documents.py's upload endpoint) — never inferred by the
ingestion pipeline or an LLM. Defaults to OTHER when not specified,
matching source_type's own "default to a known conservative value, never
guess" convention.
"""

from enum import Enum


class DocumentType(str, Enum):
    INDIAN_STANDARD = "INDIAN_STANDARD"
    REGULATORY_ORDER = "REGULATORY_ORDER"
    QCO = "QCO"
    BIS_SCHEME = "BIS_SCHEME"
    PRODUCT_MANUAL = "PRODUCT_MANUAL"
    TESTING_GUIDANCE = "TESTING_GUIDANCE"
    CERTIFICATION_GUIDANCE = "CERTIFICATION_GUIDANCE"
    OTHER = "OTHER"


DEFAULT_DOCUMENT_TYPE = DocumentType.OTHER.value

# Document types considered regulatory/procedural in nature — used by
# app/product/query_classification.py to prioritize retrieval for
# regulatory-shaped questions ("is certification mandatory?").
REGULATORY_DOCUMENT_TYPES = {
    DocumentType.REGULATORY_ORDER.value,
    DocumentType.QCO.value,
    DocumentType.CERTIFICATION_GUIDANCE.value,
}

# Document types considered technical/specification in nature — used to
# prioritize retrieval for technical-requirement questions.
TECHNICAL_DOCUMENT_TYPES = {
    DocumentType.INDIAN_STANDARD.value,
    DocumentType.PRODUCT_MANUAL.value,
    DocumentType.TESTING_GUIDANCE.value,
}

# Document types considered procedural/how-to-apply in nature.
PROCEDURAL_DOCUMENT_TYPES = {
    DocumentType.BIS_SCHEME.value,
    DocumentType.CERTIFICATION_GUIDANCE.value,
}

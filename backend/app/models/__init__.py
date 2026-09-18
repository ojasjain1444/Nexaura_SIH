"""
SQLAlchemy models for Phases 2–5.

Importing this package registers every model with `Base.metadata`, which
Alembic's env.py relies on for autogeneration. If a new model module is
added, import it here too, or Alembic will not see its table.
"""

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_citation import MessageCitation
from app.models.standard import Standard, StandardRelatedCode
from app.models.certification_scheme import CertificationScheme, CertificationStep, SchemeEligibility
from app.models.lab import Lab, LabAccreditation, LabTestCategory
from app.models.user_preference import UserPreference
from app.models.standard_document import StandardDocument
from app.models.document_page import DocumentPage
from app.models.document_feature import DocumentFeature
from app.models.document_chunk import DocumentChunk
from app.models.product_profile import ProductProfile
from app.models.regulatory_evidence import RegulatoryEvidence, RegulatoryEvidenceRelatedStandard
from app.models.standard_scope import StandardScope
from app.models.standard_requirement import StandardRequirement
from app.models.user import User
from app.models.user_session import UserSession

__all__ = [
    "Conversation",
    "Message",
    "MessageCitation",
    "Standard",
    "StandardRelatedCode",
    "CertificationScheme",
    "CertificationStep",
    "SchemeEligibility",
    "Lab",
    "LabAccreditation",
    "LabTestCategory",
    "UserPreference",
    "StandardDocument",
    "DocumentPage",
    "DocumentFeature",
    "DocumentChunk",
    "ProductProfile",
    "RegulatoryEvidence",
    "RegulatoryEvidenceRelatedStandard",
    "StandardScope",
    "StandardRequirement",
    "User",
    "UserSession",
]

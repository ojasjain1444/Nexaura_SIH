"""
StandardDocument — a real, uploaded source file being ingested and
processed. Distinct from Standard (the catalogue entry): a document can
exist and be processed before anyone links it to a Standard row, or without
ever being linked at all (e.g. a test/demo document).

Processing status values (see app/ingestion/pipeline.py for the state
machine that transitions between them):
    uploaded            file received, registered, not yet processed
    processing          pipeline actively running
    text_extracted      native/OCR text extraction finished
    features_extracted  feature-extraction stage finished
    completed           full pipeline finished successfully
    failed              pipeline aborted; see error_message

A document is not exposed to callers as "completed" until the pipeline
actually reaches that state — no stage is skipped or faked.

Phase 12 adds `document_type` (see app.product.document_type — a
controlled classification of WHAT KIND of BIS material this is, e.g.
INDIAN_STANDARD vs. QCO vs. BIS_SCHEME) and provenance fields (`source`,
`source_url`, `acquisition_date`). document_type is deliberately kept
separate from `source_type`: source_type answers "has this document's
authenticity been verified" (unverified/test/demo/verified_bis);
document_type answers "what category of BIS material is this, assuming it
is what it claims to be." Neither field is ever inferred by an LLM or the
ingestion pipeline — both are user-asserted at upload time, exactly like
source_type already is, and both default to a conservative value
(document_type -> OTHER, source_type -> unverified) rather than guessing.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StandardDocument(Base):
    __tablename__ = "standard_documents"
    __table_args__ = (
        # Prevents ingesting byte-identical content twice under different
        # filenames — the same file uploaded twice should be recognized,
        # not silently duplicated.
        UniqueConstraint("file_hash", name="uq_standard_documents_file_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Nullable: a document can be ingested before (or without ever) being
    # linked to a catalogued Standard row — matches docs/ARCHITECTURE.md §6.
    standard_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("standards.id", ondelete="SET NULL"), nullable=True, index=True
    )

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # Indexed + unique: the actual mechanism for detecting duplicate uploads.
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Indexed: GET /api/documents/{id}/status and any future "list documents
    # still processing" query filter/sort on this.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="uploaded", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extracted metadata (Step 4). Each is nullable independently — a field
    # that could not be confidently extracted stays null, it is never
    # guessed or defaulted to a placeholder value.
    extracted_standard_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extracted_edition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Phase 8: standalone publication/reaffirmation year, separate from
    # extracted_edition (e.g. "First Revision") — a BIS cover page often
    # states both independently. Nullable: left unset rather than guessed
    # when no plausible 4-digit year is found.
    extracted_publication_year: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # "demo"/"test" for synthetic pipeline-testing documents;
    # "verified_bis" is reserved for a real, confirmed-official BIS source
    # file. The ingestion CLI/API must never set "verified_bis" itself —
    # that determination is a human decision, not something the pipeline
    # infers from a PDF.
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unverified")

    # Phase 12: user-asserted classification of what KIND of BIS material
    # this is (see app.product.document_type.DocumentType for the
    # controlled value set). Defaults to "OTHER" rather than being left
    # unset, matching source_type's own "default to a conservative known
    # value" convention — never inferred by the pipeline or an LLM.
    document_type: Mapped[str] = mapped_column(String(30), nullable=False, default="OTHER")

    # Provenance (Phase 12). All independently nullable: an upload today
    # has no source_url-collection step, so it stays null rather than
    # being fabricated. `source` is a short free-text note (e.g. "user
    # upload", "manual acquisition") — deliberately not a controlled enum,
    # since provenance descriptions vary too much to usefully constrain.
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    acquisition_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    pages: Mapped[list["DocumentPage"]] = relationship(
        "DocumentPage", back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    features: Mapped[list["DocumentFeature"]] = relationship(
        "DocumentFeature", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )
    # Phase 12: at most one RegulatoryEvidence row per document. None until
    # a human explicitly records regulatory evidence for this document —
    # never created by ingestion (see app/models/regulatory_evidence.py).
    regulatory_evidence: Mapped["RegulatoryEvidence | None"] = relationship(
        "RegulatoryEvidence", back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    # At most one StandardScope row per document — see
    # app/models/standard_scope.py. None if no SCOPE clause was detected.
    scope: Mapped["StandardScope | None"] = relationship(
        "StandardScope", back_populates="document", cascade="all, delete-orphan", uselist=False
    )
    # Zero or more precomputed StandardRequirement rows — see
    # app/models/standard_requirement.py.
    requirements: Mapped[list["StandardRequirement"]] = relationship(
        "StandardRequirement", back_populates="document", cascade="all, delete-orphan"
    )

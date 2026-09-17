"""
schema.py — PostgreSQL Database Schema for Nexaura BIS Knowledge Base

Project: Nexaura (SIH 2026 — SIH26107)

Normalized schema:

    standards
        ↓
    editions
        ↓
    clauses
        ↓ (same table, parent_clause_id FK)
    sub-clauses

    tables          — extracted table records
    features        — technical parameter features
    relationships   — cross-standard links
    sources         — PDF source provenance
    processing_log  — per-PDF run history (for resume support)

DDL is written as raw SQL for portability.
Run via postgres.py init_schema().
"""

SCHEMA_DDL = """
-- ============================================================
-- standards: one row per IS standard (document-level)
-- ============================================================
CREATE TABLE IF NOT EXISTS standards (
    id                  SERIAL PRIMARY KEY,
    standard_number     VARCHAR(100) NOT NULL,
    title               TEXT,
    part                VARCHAR(50),
    section_label       VARCHAR(50),
    status              VARCHAR(50) DEFAULT 'unknown',
    ics_code            VARCHAR(50),
    technical_committee VARCHAR(100),
    source_pdf          VARCHAR(500),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(standard_number)
);

-- ============================================================
-- editions: one row per edition of a standard
-- ============================================================
CREATE TABLE IF NOT EXISTS editions (
    id                  SERIAL PRIMARY KEY,
    standard_id         INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    edition             VARCHAR(50),
    year                INTEGER,
    amendment           VARCHAR(100),
    publication_date    VARCHAR(50),
    reaffirmation_date  VARCHAR(50),
    scope               TEXT,
    foreword            TEXT,
    needs_review        BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(standard_id, edition, year)
);

-- ============================================================
-- clauses: every clause and sub-clause extracted from PDFs
-- ============================================================
CREATE TABLE IF NOT EXISTS clauses (
    id                  SERIAL PRIMARY KEY,
    standard_id         INTEGER NOT NULL REFERENCES standards(id) ON DELETE CASCADE,
    edition_id          INTEGER REFERENCES editions(id) ON DELETE SET NULL,

    -- Knowledge Unit ID (portable reference)
    knowledge_unit_id   VARCHAR(200) NOT NULL,

    -- Hierarchy
    clause              VARCHAR(100) NOT NULL,
    sub_clause          VARCHAR(100),
    parent_clause       VARCHAR(100),
    section             VARCHAR(200),
    heading             TEXT,
    content_type        VARCHAR(50) DEFAULT 'clause',
    annex               VARCHAR(50),
    depth               INTEGER DEFAULT 0,

    -- Content
    raw_text            TEXT,
    clean_text          TEXT,
    summary             TEXT,

    -- Semantic features (Group C) stored as JSON arrays
    keywords            JSONB DEFAULT '[]',
    entities            JSONB DEFAULT '[]',
    product             JSONB DEFAULT '[]',
    application         JSONB DEFAULT '[]',
    material            JSONB DEFAULT '[]',
    process             JSONB DEFAULT '[]',
    industry            JSONB DEFAULT '[]',
    domain              JSONB DEFAULT '[]',

    -- Technical features (Group D)
    technical_parameters JSONB DEFAULT '[]',

    -- Requirement features (Group E)
    requirements        JSONB DEFAULT '[]',

    -- Cross-references (Group F)
    cross_references    JSONB DEFAULT '[]',

    -- Provenance
    page_start          INTEGER DEFAULT 0,
    page_end            INTEGER DEFAULT 0,
    source_pdf          VARCHAR(500),
    extraction_method   VARCHAR(50) DEFAULT 'gemini_flash',
    ocr_confidence      FLOAT DEFAULT 0.0,

    -- Quality
    needs_review        BOOLEAN DEFAULT FALSE,
    validation_status   VARCHAR(50) DEFAULT 'pending',
    review_reason       TEXT,

    -- Search text (combined for BM25 + embedding)
    search_text         TEXT,

    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(knowledge_unit_id)
);

-- Full-text search index on search_text
CREATE INDEX IF NOT EXISTS idx_clauses_search ON clauses USING GIN(to_tsvector('english', COALESCE(search_text, '')));
CREATE INDEX IF NOT EXISTS idx_clauses_standard ON clauses(standard_id);
CREATE INDEX IF NOT EXISTS idx_clauses_clause ON clauses(clause);
CREATE INDEX IF NOT EXISTS idx_clauses_content_type ON clauses(content_type);
CREATE INDEX IF NOT EXISTS idx_clauses_validation ON clauses(validation_status);

-- ============================================================
-- tables: extracted tabular data
-- ============================================================
CREATE TABLE IF NOT EXISTS document_tables (
    id                  SERIAL PRIMARY KEY,
    table_id            VARCHAR(200) NOT NULL,
    standard_id         INTEGER REFERENCES standards(id) ON DELETE CASCADE,
    clause_id           INTEGER REFERENCES clauses(id) ON DELETE SET NULL,
    source_table_ref    VARCHAR(100),
    clause              VARCHAR(100),
    page                INTEGER DEFAULT 0,
    caption             TEXT,
    columns             JSONB DEFAULT '[]',
    rows                JSONB DEFAULT '[]',
    units               JSONB DEFAULT '[]',
    footnotes           JSONB DEFAULT '[]',
    search_text         TEXT,
    source_pdf          VARCHAR(500),
    standard_number     VARCHAR(100),
    needs_review        BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(table_id)
);

-- ============================================================
-- features: individual technical parameter records
-- ============================================================
CREATE TABLE IF NOT EXISTS features (
    id                  SERIAL PRIMARY KEY,
    clause_id           INTEGER REFERENCES clauses(id) ON DELETE CASCADE,
    knowledge_unit_id   VARCHAR(200),
    standard_number     VARCHAR(100),
    parameter_name      VARCHAR(200) NOT NULL,
    value               FLOAT,
    value_str           VARCHAR(200),
    unit                VARCHAR(100),
    operator            VARCHAR(50),
    range_min           FLOAT,
    range_max           FLOAT,
    material            VARCHAR(200),
    context             TEXT,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_features_std ON features(standard_number);
CREATE INDEX IF NOT EXISTS idx_features_param ON features(parameter_name);

-- ============================================================
-- relationships: cross-standard links (evidence-based only)
-- ============================================================
CREATE TABLE IF NOT EXISTS relationships (
    id                  SERIAL PRIMARY KEY,
    from_standard_id    INTEGER REFERENCES standards(id) ON DELETE CASCADE,
    to_standard_ref     VARCHAR(200) NOT NULL,
    relation_type       VARCHAR(100) NOT NULL,
    source_evidence     TEXT,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_standard_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relation_type);

-- ============================================================
-- sources: PDF source provenance
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id                  SERIAL PRIMARY KEY,
    standard_id         INTEGER REFERENCES standards(id) ON DELETE CASCADE,
    source_pdf          VARCHAR(500) NOT NULL,
    file_hash           VARCHAR(64),
    file_size_bytes     BIGINT,
    total_pages         INTEGER,
    processed_pages     INTEGER,
    gemini_pages        INTEGER DEFAULT 0,
    text_pages          INTEGER DEFAULT 0,
    scanned_pages       INTEGER DEFAULT 0,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(source_pdf, file_hash)
);

-- ============================================================
-- processing_log: per-PDF run history (for resume support)
-- ============================================================
CREATE TABLE IF NOT EXISTS processing_log (
    id                  SERIAL PRIMARY KEY,
    source_pdf          VARCHAR(500) NOT NULL,
    file_hash           VARCHAR(64),
    status              VARCHAR(50) NOT NULL,  -- pending | processing | completed | failed
    clauses_extracted   INTEGER DEFAULT 0,
    tables_extracted    INTEGER DEFAULT 0,
    features_extracted  INTEGER DEFAULT 0,
    avg_confidence      FLOAT DEFAULT 0.0,
    error_message       TEXT,
    started_at          TIMESTAMP WITH TIME ZONE,
    completed_at        TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(file_hash)
);

CREATE INDEX IF NOT EXISTS idx_processing_log_status ON processing_log(status);
CREATE INDEX IF NOT EXISTS idx_processing_log_hash ON processing_log(file_hash);
"""


def get_schema_ddl() -> str:
    """Return the full PostgreSQL DDL for schema initialization."""
    return SCHEMA_DDL

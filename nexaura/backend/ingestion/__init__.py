"""
nexaura/backend/ingestion/__init__.py

Ingestion sub-package for the Nexaura PDF Intelligence Pipeline.

Modules:
    pdf_detector      — PyMuPDF PDF classification (text/scanned/mixed/invalid)
    text_extractor    — Direct text extraction for text-layer pages
    gemini_ocr        — Gemini Flash document intelligence
    layout_parser     — Layout and heading reconstruction
    clause_parser     — Clause hierarchy builder
    table_parser      — Structured table extraction
    metadata_extractor— Document-level metadata extraction
    feature_extractor — Feature groups A-F + KnowledgeUnit model
    cleaner           — Data cleaning (raw_text → clean_text)
    validator         — Record validation and flagging
    graph_builder     — Knowledge graph construction
    pipeline          — End-to-end orchestration
"""

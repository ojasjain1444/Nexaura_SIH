"""
Nexaura BIS Knowledge Base Builder.

Project: Smart India Hackathon 2026 — Problem Statement SIH26107
"AI Assistant for Indian Standards and BIS Services"

This package implements the PDF Document Intelligence Pipeline:

  RAW BIS PDFs
  → Gemini Flash Document Intelligence
  → Structured Clause-Level Knowledge
  → Feature Extraction
  → PostgreSQL + Qdrant + BM25
  → Feature-Based Similarity Retrieval
  → Citation-Grounded Answering

The chatbot does NOT perform OCR at query time.
OCR and document processing happen during OFFLINE INGESTION only.
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "Nexaura Team"
__project__ = "SIH 2026 — SIH26107"

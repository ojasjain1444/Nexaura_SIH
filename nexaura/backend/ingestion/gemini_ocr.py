"""
gemini_ocr.py — Phase 2b: Gemini Flash Document Intelligence

Project: Nexaura (SIH 2026 — SIH26107)

Uses the Gemini Flash API as the primary OCR and document-understanding
engine for BIS standards PDFs. Gemini is NOT used as a simple text extractor;
it performs:

    - Layout understanding
    - Clause and sub-clause detection
    - Table extraction
    - Heading detection
    - Document hierarchy reconstruction
    - Technical value extraction
    - Reference extraction

Cost control:
    - File/page hash-based caching (no re-calls for already-processed pages)
    - Configurable retries with exponential backoff
    - Failed-page queue (logged, not silently discarded)
    - Only called for pages where requires_gemini = True

Security:
    - GEMINI_API_KEY loaded from environment variable only
    - Model name configurable via GEMINI_MODEL env var
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional
import xxhash

logger = logging.getLogger(__name__)


# =============================================================================
# Gemini JSON Schema (returned by API)
# =============================================================================

GEMINI_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "standard_number":  {"type": "string"},
        "title":            {"type": "string"},
        "edition":          {"type": "string"},
        "year":             {"type": ["integer", "null"]},
        "part":             {"type": ["string", "null"]},
        "amendment":        {"type": ["string", "null"]},
        "scope":            {"type": ["string", "null"]},
        "foreword":         {"type": ["string", "null"]},
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause":       {"type": "string"},
                    "parent":       {"type": ["string", "null"]},
                    "heading":      {"type": ["string", "null"]},
                    "text":         {"type": "string"},
                    "page":         {"type": "integer"},
                    "content_type": {"type": "string"},
                    "notes":        {"type": "array", "items": {"type": "string"}},
                },
                "required": ["clause", "text", "page"],
            },
        },
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "table_id":  {"type": "string"},
                    "clause":    {"type": ["string", "null"]},
                    "page":      {"type": "integer"},
                    "caption":   {"type": ["string", "null"]},
                    "columns":   {"type": "array", "items": {"type": "string"}},
                    "rows":      {"type": "array", "items": {"type": "array"}},
                    "units":     {"type": "array", "items": {"type": "string"}},
                    "footnotes": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "definitions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term":       {"type": "string"},
                    "definition": {"type": "string"},
                    "clause":     {"type": ["string", "null"]},
                    "page":       {"type": "integer"},
                },
            },
        },
        "annexures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "annex_id": {"type": "string"},
                    "title":    {"type": "string"},
                    "text":     {"type": "string"},
                    "page":     {"type": "integer"},
                },
            },
        },
        "references": {
            "type": "array",
            "items": {"type": "string"},
        },
        "bibliography": {
            "type": "array",
            "items": {"type": "string"},
        },
        "pages_processed": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "needs_review":   {"type": "boolean"},
        "review_reason":  {"type": ["string", "null"]},
    },
    "required": ["standard_number", "clauses", "needs_review"],
}


# =============================================================================
# System Instruction
# =============================================================================

GEMINI_SYSTEM_INSTRUCTION = """You are a Bureau of Indian Standards (BIS) document intelligence engine.

Your task is to extract structured information from BIS Indian Standards (IS) documents.

STRICT RULES:
1. Return ONLY valid JSON — never return prose, explanations, or markdown.
2. Never invent clause numbers. Extract only those explicitly present in the document.
3. Never invent standard numbers, edition years, or amendment numbers.
4. Never fabricate technical values, units, dimensions, or requirements.
5. Preserve all technical values exactly as written (e.g. "80 μm" not "80 micrometers").
6. Preserve clause numbering exactly (e.g. "5.2.1", "A-1", "Table 4").
7. Preserve table structure — do not flatten tables to plain text.
8. If a section is unreadable or unclear, set needs_review: true and explain in review_reason.
9. Preserve the full hierarchical structure (Standard → Part → Section → Clause → Sub-clause).
10. For requirement clauses, preserve exact wording ("shall", "shall not", "must", etc.).
11. Never guess — if uncertain, mark needs_review: true.

CONTENT TO EXTRACT:
- Standard number (e.g. "IS 1234")
- Title
- Edition / Year
- Part number (if applicable)
- Amendment information (if applicable)
- Scope clause
- Foreword
- All clauses and sub-clauses with their full text
- All tables with structured columns and rows
- Definitions section
- Annexures
- References and bibliography

Return the extracted information as a single JSON object matching the provided schema."""


# =============================================================================
# Result Model
# =============================================================================

class GeminiExtractionResult:
    """Result of Gemini Flash document extraction."""

    def __init__(
        self,
        pdf_name: str,
        pages_processed: list[int],
        data: dict[str, Any],
        raw_response: str,
        success: bool,
        error: Optional[str] = None,
        needs_review: bool = False,
        confidence: float = 1.0,
        cache_hit: bool = False,
        retry_count: int = 0,
    ) -> None:
        self.pdf_name = pdf_name
        self.pages_processed = pages_processed
        self.data = data
        self.raw_response = raw_response
        self.success = success
        self.error = error
        self.needs_review = needs_review or data.get("needs_review", False)
        self.confidence = confidence
        self.cache_hit = cache_hit
        self.retry_count = retry_count

    @property
    def standard_number(self) -> str:
        return self.data.get("standard_number", "unknown")

    @property
    def clauses(self) -> list[dict]:
        return self.data.get("clauses", [])

    @property
    def tables(self) -> list[dict]:
        return self.data.get("tables", [])

    @property
    def definitions(self) -> list[dict]:
        return self.data.get("definitions", [])

    @property
    def annexures(self) -> list[dict]:
        return self.data.get("annexures", [])

    @property
    def references(self) -> list[str]:
        return self.data.get("references", [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf_name": self.pdf_name,
            "pages_processed": self.pages_processed,
            "success": self.success,
            "error": self.error,
            "needs_review": self.needs_review,
            "confidence": self.confidence,
            "cache_hit": self.cache_hit,
            "retry_count": self.retry_count,
            **self.data,
        }


# =============================================================================
# Gemini OCR Client
# =============================================================================

class GeminiOCR:
    """
    Gemini Flash API client for BIS document intelligence.

    Features:
    - Configurable model name (never hardcoded)
    - Page-level hash caching (avoids re-calling Gemini for processed pages)
    - Exponential backoff retry logic
    - Structured JSON response parsing with fallback
    - Failed-page logging
    - Rate limit handling
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 5,
        retry_backoff_base: float = 2.0,
        retry_backoff_max: float = 60.0,
        request_timeout: int = 120,
        cache_dir: Optional[Path] = None,
        cache_responses: bool = True,
        failed_log_path: Optional[Path] = None,
    ) -> None:
        """
        Args:
            api_key: Gemini API key. Defaults to GEMINI_API_KEY env var.
            model: Gemini model name. Defaults to GEMINI_MODEL env var,
                   then "gemini-2.0-flash".
            max_retries: Maximum retry attempts on failure.
            retry_backoff_base: Exponential backoff base (seconds).
            retry_backoff_max: Maximum backoff cap (seconds).
            request_timeout: Seconds before request times out.
            cache_dir: Directory to cache Gemini responses by file hash.
            cache_responses: If True, cache and reuse responses.
            failed_log_path: JSONL file to log failed pages.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY must be set as an environment variable or passed to GeminiOCR()."
            )

        # Model is always configurable — never hardcoded
        self.model = (
            model
            or os.environ.get("GEMINI_MODEL", "")
            or "gemini-2.0-flash"
        )
        logger.info("GeminiOCR initialized with model: %s", self.model)

        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base
        self.retry_backoff_max = retry_backoff_max
        self.request_timeout = request_timeout
        self.cache_responses = cache_responses

        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir and cache_responses:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.failed_log_path = Path(failed_log_path) if failed_log_path else None
        if self.failed_log_path:
            self.failed_log_path.parent.mkdir(parents=True, exist_ok=True)

        self._client = None  # lazy initialization

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def process_pdf(
        self,
        pdf_path: Path,
        file_hash: Optional[str] = None,
    ) -> GeminiExtractionResult:
        """
        Process an entire PDF through Gemini Flash.

        Sends the full PDF to Gemini using the Files API for complete
        document understanding (preferred approach for BIS standards).

        Args:
            pdf_path: Path to the PDF file.
            file_hash: Pre-computed file hash (from PDFDetector).
                       Used for cache lookup.

        Returns:
            GeminiExtractionResult
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            return self._failure_result(
                pdf_path.name, [], f"File not found: {pdf_path}"
            )

        # Compute hash if not provided
        if not file_hash:
            file_hash = self._hash_file(pdf_path)

        # Check cache
        if self.cache_responses and self.cache_dir:
            cached = self._load_cache(file_hash)
            if cached is not None:
                logger.info("Cache hit for %s (hash=%s)", pdf_path.name, file_hash[:12])
                return GeminiExtractionResult(
                    pdf_name=pdf_path.name,
                    pages_processed=cached.get("pages_processed", []),
                    data=cached,
                    raw_response=json.dumps(cached),
                    success=True,
                    cache_hit=True,
                )

        logger.info("Sending %s to Gemini (%s)", pdf_path.name, self.model)
        return self._call_gemini_with_pdf(pdf_path, file_hash)

    # -------------------------------------------------------------------------
    # Internal: Gemini API calls
    # -------------------------------------------------------------------------

    def _get_client(self):
        """Lazy-initialize the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError as e:
                raise ImportError(
                    "google-generativeai required: pip install google-generativeai"
                ) from e
            genai.configure(api_key=self.api_key)
            self._client = genai
        return self._client

    def _call_gemini_with_pdf(
        self,
        pdf_path: Path,
        file_hash: str,
    ) -> GeminiExtractionResult:
        """Upload PDF to Gemini Files API and request structured extraction."""
        genai = self._get_client()

        prompt = self._build_prompt()
        last_error: Optional[str] = None
        retry_count = 0

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                backoff = min(
                    self.retry_backoff_base ** attempt,
                    self.retry_backoff_max,
                )
                logger.warning(
                    "Retry %d/%d for %s (backoff=%.1fs): %s",
                    attempt, self.max_retries, pdf_path.name, backoff, last_error,
                )
                time.sleep(backoff)

            try:
                # Upload PDF via Files API
                logger.debug("Uploading %s to Gemini Files API...", pdf_path.name)
                uploaded_file = genai.upload_file(
                    path=str(pdf_path),
                    mime_type="application/pdf",
                )

                # Create generative model
                model = genai.GenerativeModel(
                    model_name=self.model,
                    system_instruction=GEMINI_SYSTEM_INSTRUCTION,
                    generation_config={
                        "temperature": 0.0,
                        "response_mime_type": "application/json",
                    },
                )

                # Generate content
                response = model.generate_content(
                    [uploaded_file, prompt],
                    request_options={"timeout": self.request_timeout},
                )

                raw_text = response.text.strip()
                parsed = self._parse_json_response(raw_text, pdf_path.name)

                if parsed is None:
                    last_error = "Failed to parse JSON response"
                    retry_count += 1
                    continue

                # Successful extraction
                result = GeminiExtractionResult(
                    pdf_name=pdf_path.name,
                    pages_processed=parsed.get("pages_processed", []),
                    data=parsed,
                    raw_response=raw_text,
                    success=True,
                    needs_review=parsed.get("needs_review", False),
                    confidence=self._estimate_confidence(parsed),
                    retry_count=retry_count,
                )

                # Save to cache
                if self.cache_responses and self.cache_dir:
                    self._save_cache(file_hash, parsed)

                logger.info(
                    "Gemini extraction complete: %s | clauses=%d tables=%d review=%s",
                    pdf_path.name,
                    len(parsed.get("clauses", [])),
                    len(parsed.get("tables", [])),
                    parsed.get("needs_review", False),
                )

                # Clean up uploaded file
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass  # Non-critical

                return result

            except Exception as exc:
                last_error = str(exc)
                retry_count += 1

                # Detect rate limit errors
                exc_str = str(exc).lower()
                if "rate" in exc_str or "quota" in exc_str or "429" in exc_str:
                    extra_wait = 30
                    logger.warning("Rate limit hit — waiting %ds extra", extra_wait)
                    time.sleep(extra_wait)

        # All retries exhausted
        logger.error(
            "Gemini extraction FAILED for %s after %d retries: %s",
            pdf_path.name, self.max_retries, last_error,
        )
        self._log_failure(pdf_path.name, last_error or "Unknown error")

        return self._failure_result(pdf_path.name, [], last_error or "Unknown error")

    # -------------------------------------------------------------------------
    # Prompt builder
    # -------------------------------------------------------------------------

    def _build_prompt(self) -> str:
        """Build the extraction prompt for Gemini."""
        return """Extract all content from this Bureau of Indian Standards (BIS) document.

Return a single JSON object with the following structure:

{
  "standard_number": "IS XXXX",
  "title": "Full title of the standard",
  "edition": "Year or edition string",
  "year": 2024,
  "part": null,
  "amendment": null,
  "scope": "Full text of scope clause",
  "foreword": "Full foreword text if present",
  "clauses": [
    {
      "clause": "5.2.1",
      "parent": "5.2",
      "heading": "Chemical Composition",
      "text": "Full clause text exactly as written",
      "page": 37,
      "content_type": "requirement",
      "notes": []
    }
  ],
  "tables": [
    {
      "table_id": "Table 1",
      "clause": "6.3",
      "page": 42,
      "caption": "Table caption",
      "columns": ["Grade", "Thickness", "Requirement"],
      "rows": [["A", "2.0 mm", "..."], ["B", "3.0 mm", "..."]],
      "units": ["mm"],
      "footnotes": []
    }
  ],
  "definitions": [
    {
      "term": "term name",
      "definition": "exact definition text",
      "clause": "3.1",
      "page": 5
    }
  ],
  "annexures": [
    {
      "annex_id": "Annex A",
      "title": "Annex title",
      "text": "Full annex text",
      "page": 55
    }
  ],
  "references": ["IS 456", "IS 269"],
  "bibliography": [],
  "pages_processed": [1, 2, 3],
  "needs_review": false,
  "review_reason": null
}

CRITICAL RULES:
- Return ONLY this JSON — no other text
- Preserve exact technical values (numbers, units, symbols)
- Preserve exact clause numbers as they appear
- Do not invent or infer any information
- If unreadable, set needs_review: true"""

    # -------------------------------------------------------------------------
    # Parsing helpers
    # -------------------------------------------------------------------------

    def _parse_json_response(
        self,
        raw_text: str,
        pdf_name: str,
    ) -> Optional[dict[str, Any]]:
        """Parse Gemini JSON response, with fallback stripping."""
        if not raw_text:
            logger.warning("Empty response from Gemini for %s", pdf_name)
            return None

        # Try direct parse
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences if present
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            # Remove first and last fence lines
            inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass

        # Find JSON object in response
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw_text[start:end])
            except json.JSONDecodeError:
                pass

        logger.error(
            "Cannot parse Gemini response for %s. Preview: %s",
            pdf_name, raw_text[:300],
        )
        return None

    def _estimate_confidence(self, data: dict[str, Any]) -> float:
        """Estimate extraction confidence from response data."""
        if data.get("needs_review"):
            return 0.60

        clauses = data.get("clauses", [])
        if not clauses:
            return 0.40

        # Check for empty/very short clauses
        short_clauses = sum(1 for c in clauses if len(c.get("text", "")) < 10)
        if short_clauses > len(clauses) * 0.3:
            return 0.70

        return 0.95

    # -------------------------------------------------------------------------
    # Cache helpers
    # -------------------------------------------------------------------------

    def _cache_path(self, file_hash: str) -> Path:
        """Return the cache file path for a given hash."""
        return self.cache_dir / f"{file_hash}.json"

    def _load_cache(self, file_hash: str) -> Optional[dict]:
        """Load cached response by file hash."""
        if not self.cache_dir:
            return None
        cache_file = self._cache_path(file_hash)
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Cache load failed for %s: %s", file_hash[:12], exc)
        return None

    def _save_cache(self, file_hash: str, data: dict) -> None:
        """Save response to cache."""
        if not self.cache_dir:
            return
        cache_file = self._cache_path(file_hash)
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Cache save failed: %s", exc)

    # -------------------------------------------------------------------------
    # Failure logging
    # -------------------------------------------------------------------------

    def _log_failure(self, pdf_name: str, error: str) -> None:
        """Log failed extraction to JSONL file."""
        if not self.failed_log_path:
            return
        import json as _json
        from datetime import datetime, timezone
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pdf_name": pdf_name,
            "error": error,
        }
        try:
            with open(self.failed_log_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(record) + "\n")
        except Exception:
            pass

    @staticmethod
    def _failure_result(
        pdf_name: str,
        pages: list[int],
        error: str,
    ) -> GeminiExtractionResult:
        """Return a failure result."""
        return GeminiExtractionResult(
            pdf_name=pdf_name,
            pages_processed=pages,
            data={
                "standard_number": "unknown",
                "clauses": [],
                "tables": [],
                "needs_review": True,
                "review_reason": error,
            },
            raw_response="",
            success=False,
            error=error,
            needs_review=True,
            confidence=0.0,
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Compute xxhash of a file."""
        h = xxhash.xxh64()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

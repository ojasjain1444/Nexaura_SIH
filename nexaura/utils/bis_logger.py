"""
bis_logger.py — Structured Logging Setup for Nexaura

Project: Nexaura (SIH 2026 — SIH26107)

Provides:
    - Structured JSON log output (for log aggregation)
    - Colour console output (for development)
    - Per-run log file with rotation
    - Module-level logger factory
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_nexaura_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    json_output: bool = False,
) -> logging.Logger:
    """
    Configure the root nexaura logger.

    Args:
        level: Log level string (DEBUG | INFO | WARNING | ERROR).
        log_file: Path to rotating log file. None = console only.
        json_output: If True, use JSON-structured output in file handler.

    Returns:
        Root nexaura logger.
    """
    root = logging.getLogger("nexaura")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if root.handlers:
        root.handlers.clear()

    # Console handler — human readable
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    # File handler — rotating, JSON or plain
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB per file
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        if json_output:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(PlainFormatter())
        root.addHandler(file_handler)

    # Suppress noisy external libraries
    for lib in ("httpx", "httpcore", "urllib3", "sentence_transformers",
                 "transformers", "google.auth", "qdrant_client"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the nexaura namespace."""
    return logging.getLogger(f"nexaura.{name}")


# =============================================================================
# Formatters
# =============================================================================

class ConsoleFormatter(logging.Formatter):
    """Colour console formatter for development."""

    COLOURS = {
        "DEBUG":    "\033[36m",   # Cyan
        "INFO":     "\033[32m",   # Green
        "WARNING":  "\033[33m",   # Yellow
        "ERROR":    "\033[31m",   # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self.COLOURS.get(record.levelname, "")
        level  = f"{colour}{record.levelname:<8}{self.RESET}"
        name   = record.name.replace("nexaura.", "")
        msg    = record.getMessage()
        ts     = self.formatTime(record, "%H:%M:%S")

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return f"{ts} | {level} | {name:<30} | {msg}"


class PlainFormatter(logging.Formatter):
    """Plain text file formatter."""

    def format(self, record: logging.LogRecord) -> str:
        ts  = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts} | {record.levelname:<8} | {record.name} | {msg}"


class JSONFormatter(logging.Formatter):
    """JSON-structured file formatter for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone
        data = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
            "module":  record.module,
            "line":    record.lineno,
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)

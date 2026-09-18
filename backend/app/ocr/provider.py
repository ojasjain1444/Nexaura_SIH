"""
OCR provider abstraction.

Per docs/ARCHITECTURE.md's recommendation: Tesseract is the local, offline,
zero-API-key default (see TesseractOCRProvider below), but nothing in the
ingestion pipeline is allowed to import Tesseract directly — it only ever
talks to this `OCRProvider` interface, so a future cloud OCR provider can
be swapped in via configuration without touching pipeline code.
"""

from dataclasses import dataclass
from typing import Protocol

from PIL import Image


@dataclass
class OCRResult:
    text: str
    confidence: float | None  # 0.0-1.0, or None if the provider doesn't report one


class OCRProvider(Protocol):
    def extract_text(self, image: Image.Image) -> OCRResult: ...

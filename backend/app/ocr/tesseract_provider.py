"""
Tesseract-backed OCRProvider implementation.

Requires the `tesseract` binary to be installed on the system (not a pip
package) — e.g. `brew install tesseract` on macOS. This module raises a
clear error at call time (not at import time) if the binary is missing, so
importing app.ocr does not itself require Tesseract to be present.
"""

import pytesseract
from PIL import Image

from app.ocr.provider import OCRResult


class TesseractOCRProvider:
    def extract_text(self, image: Image.Image) -> OCRResult:
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(
                "Tesseract OCR binary not found. Install it with `brew install tesseract` (macOS) "
                "and ensure it is on PATH."
            ) from exc

        words = []
        confidences = []
        for text, conf in zip(data["text"], data["conf"]):
            text = text.strip()
            if not text:
                continue
            words.append(text)
            conf_value = float(conf)
            if conf_value >= 0:  # Tesseract reports -1 for non-text regions
                confidences.append(conf_value)

        full_text = " ".join(words)
        avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else None
        return OCRResult(text=full_text, confidence=avg_confidence)

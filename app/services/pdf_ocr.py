from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pdf_pages_ocr(path: Path, *, max_pages: int) -> list[tuple[int, str]]:
    """
    Extraction OCR optionnelle (scans). Nécessite : ``pdf2image``, ``Pillow``, ``pytesseract``
    et binaire Tesseract (+ Poppler pour pdf2image). Sinon retourne [].
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.debug("pdf_ocr: pdf2image/pytesseract non installés (extra « ocr »).")
        return []
    out: list[tuple[int, str]] = []
    try:
        images = convert_from_path(str(path), first_page=1, last_page=max_pages, dpi=200)
    except Exception as exc:
        logger.warning("pdf_ocr: convert_from_path failed: %s", exc)
        return []
    for i, img in enumerate(images, start=1):
        try:
            text = pytesseract.image_to_string(img, lang="fra+eng") or ""
        except Exception as exc:
            logger.warning("pdf_ocr: tesseract page %s: %s", i, exc)
            continue
        t = text.strip()
        if t:
            out.append((i, t))
    return out

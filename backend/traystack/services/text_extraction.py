"""Per-page extraction with conservative, explicitly heuristic quality checks."""

import math
import re
from dataclasses import asdict, dataclass, field
from importlib.metadata import version
from pathlib import Path
from statistics import mean
from typing import Any

import pymupdf
import pytesseract
from PIL import Image, ImageOps

from traystack.services.normalization import normalize_for_search


class ProcessingError(Exception):
    """Only fixed reason codes may cross the worker/API boundary."""


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    extraction_method: str
    status: str = "complete"
    quality_status: str = "no_known_issue"
    quality_warnings: list[str] = field(default_factory=list)
    confidence: float | None = None
    layout_metadata: dict[str, Any] = field(default_factory=dict)
    normalized_text: str = ""
    start_offset: int = 0
    end_offset: int = 0


@dataclass
class Extraction:
    pages: list[ExtractedPage]
    processor_versions: dict[str, str]
    plain_text: str = ""
    normalized_text: str = ""
    status: str = "unavailable"
    quality_status: str = "unassessed"
    quality_warnings: list[str] = field(default_factory=list)
    pages_processed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_page(page: ExtractedPage, manual_review: bool) -> ExtractedPage:
    if "\x00" in page.text:
        page.text = page.text.replace("\x00", "\ufffd")
        page.quality_warnings.append("null_character_replaced")
    if not page.text.strip():
        page.status = "unavailable"
        page.quality_warnings.append("no_text_detected")
    elif (
        "\ufffd" in page.text
        or len(re.findall(r"[^\w\s.,;:!?()\[\]{}'\"/%+€$£&@#=<>*\\–—-]", page.text))
        > max(5, len(page.text) * 0.08)
        or sum(character.isalnum() for character in page.text) < 10
    ):
        page.quality_warnings.append("suspicious_text")
    if manual_review:
        page.quality_warnings.append("manual_review_requested")
    page.quality_warnings = sorted(set(page.quality_warnings))
    if page.quality_warnings or page.status != "complete":
        page.quality_status = "needs_review"
    return page


def ocr_page(image: Image.Image, page_number: int, parameters: dict[str, Any]) -> ExtractedPage:
    # Work with one bounded image. Respect camera orientation but never rewrite the source.
    image = ImageOps.exif_transpose(image).convert("RGB")
    max_pixels = parameters["max_pixels"]
    if image.width * image.height > max_pixels:
        scale = math.sqrt(max_pixels / (image.width * image.height))
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    try:
        data = pytesseract.image_to_data(
            image,
            lang=parameters["ocr_languages"],
            config="--psm 3",
            output_type=pytesseract.Output.DICT,
            timeout=parameters["ocr_timeout_seconds"],
        )
    except (pytesseract.TesseractError, OSError):
        return ExtractedPage(
            page_number, "", "ocr", status="unavailable", quality_warnings=["ocr_failed"]
        )
    except RuntimeError:
        return ExtractedPage(
            page_number, "", "ocr", status="unavailable", quality_warnings=["ocr_timeout"]
        )
    lines: dict[tuple[int, int, int], list[str]] = {}
    words, confidences = [], []
    for index, text in enumerate(data["text"]):
        if not text.strip():
            continue
        key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
        lines.setdefault(key, []).append(text)
        confidence = float(data["conf"][index])
        if confidence >= 0:
            confidences.append(confidence)
        words.append(
            {
                "text": text,
                "bbox": [
                    data["left"][index],
                    data["top"][index],
                    data["width"][index],
                    data["height"][index],
                ],
                "confidence": confidence if confidence >= 0 else None,
            }
        )
    confidence = mean(confidences) if confidences else None
    warnings = []
    if confidence is None:
        warnings.append("ocr_confidence_unavailable")
    elif confidence < parameters["ocr_min_mean_confidence"] or (
        sum(score < 50 for score in confidences) / len(confidences) > 0.2
    ):
        warnings.append("low_ocr_confidence")
    return ExtractedPage(
        page_number,
        "\n".join(" ".join(words) for words in lines.values()),
        "ocr",
        quality_warnings=warnings,
        confidence=confidence,
        layout_metadata={
            "coordinate_space": "image_pixels",
            "width": image.width,
            "height": image.height,
            "words": words,
        },
    )


def extract_source(path: Path, mime_type: str, parameters: dict[str, Any]) -> Extraction:
    versions = {
        "pymupdf": pymupdf.VersionBind,
        "pillow": version("pillow"),
        "pytesseract": version("pytesseract"),
    }
    try:
        versions["tesseract"] = str(pytesseract.get_tesseract_version())
    except (OSError, pytesseract.TesseractNotFoundError):
        versions["tesseract"] = "unavailable"
    pages = []
    if mime_type == "application/pdf":
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ProcessingError("encrypted_pdf")
            if not 0 < document.page_count <= parameters["max_pages"]:
                raise ProcessingError("source_page_limit_exceeded")
            for index in range(document.page_count):
                try:
                    source_page = document[index]
                    embedded = source_page.get_text("text", sort=True)
                    # Any raster content may contain contract text, even beside an embedded header.
                    if len(embedded.strip()) >= 20 and not source_page.get_images():
                        words = source_page.get_text("words", sort=True)
                        page = ExtractedPage(
                            index + 1,
                            embedded,
                            "embedded_pdf_text",
                            layout_metadata={
                                "coordinate_space": "pdf_points",
                                "width": source_page.rect.width,
                                "height": source_page.rect.height,
                                "words": [
                                    {"bbox": list(word[:4]), "text": word[4]} for word in words
                                ],
                            },
                        )
                    else:
                        scale = parameters["ocr_dpi"] / 72
                        area = source_page.rect.width * source_page.rect.height
                        scale = min(scale, math.sqrt(parameters["max_pixels"] / max(1, area)))
                        pixmap = source_page.get_pixmap(
                            matrix=pymupdf.Matrix(scale, scale),
                            alpha=False,
                            colorspace=pymupdf.csRGB,
                        )
                        image = Image.frombytes(
                            "RGB", (pixmap.width, pixmap.height), pixmap.samples
                        )
                        page = ocr_page(image, index + 1, parameters)
                except (RuntimeError, ValueError, OSError):
                    page = ExtractedPage(
                        index + 1,
                        "",
                        "unavailable",
                        status="unavailable",
                        quality_warnings=["page_extraction_failed"],
                    )
                pages.append(assess_page(page, parameters["requires_manual_review"]))
    elif mime_type in {"image/jpeg", "image/png"}:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ProcessingError("multi_frame_image_unsupported")
            page = ocr_page(image, 1, parameters)
        pages.append(assess_page(page, parameters["requires_manual_review"]))
    else:
        raise ProcessingError("unsupported_source_type")
    return build_canonical_text(Extraction(pages, versions))


def build_canonical_text(result: Extraction) -> Extraction:
    result.plain_text = "\n\f\n".join(page.text for page in result.pages)
    # Normalizing separately by page permits exact normalized page offsets. Empty pages
    # occupy a zero-length span. The full string equals normalization of plain_text.
    normalized = ""
    for page in result.pages:
        page.normalized_text = normalize_for_search(page.text)
        if normalized and page.normalized_text:
            normalized += " "
        page.start_offset = len(normalized)
        normalized += page.normalized_text
        page.end_offset = len(normalized)
    result.normalized_text = normalized
    assert normalized == normalize_for_search(result.plain_text)
    result.pages_processed = sum(page.status == "complete" for page in result.pages)
    result.status = (
        "complete"
        if result.pages_processed == len(result.pages)
        else ("partial" if result.pages_processed else "unavailable")
    )
    result.quality_warnings = sorted(
        {warning for page in result.pages for warning in page.quality_warnings}
    )
    qualities = {page.quality_status for page in result.pages}
    result.quality_status = (
        "needs_review"
        if "needs_review" in qualities
        else ("unassessed" if "unassessed" in qualities else "no_known_issue")
    )
    return result

import re
import warnings
from pathlib import PurePosixPath
from typing import BinaryIO

import pymupdf
from PIL import Image, UnidentifiedImageError

from traystack.services.storage import InvalidUpload
from traystack.services.text_documents import TEXT_TYPES, decode_text

TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    **TEXT_TYPES,
}


def safe_filename(filename: str | None) -> str:
    name = PurePosixPath((filename or "upload").replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    return name[:255] or "upload"


def validate_file(stream: BinaryIO, filename: str) -> str:
    """Inspect actual content, preserving the stream and original bytes."""
    extension = PurePosixPath(filename).suffix.lower()
    expected = TYPES.get(extension)
    if not expected:
        raise InvalidUpload("Supported file extensions: .pdf, .jpg, .jpeg, .png, .txt, .htm, .html")
    stream.seek(0)
    signature = stream.read(8)
    stream.seek(0)
    try:
        if expected in TEXT_TYPES.values():
            try:
                decode_text(stream.read())
            except (UnicodeDecodeError, ValueError):
                raise InvalidUpload(
                    "Text/HTML must be non-empty UTF-8 without binary control characters"
                ) from None
        elif expected == "application/pdf":
            if not signature.startswith(b"%PDF-"):
                raise InvalidUpload("File content does not match PDF extension")
            # Bounded by the upload limit; extraction/rendering is deferred to a worker.
            with pymupdf.open(stream=stream.read(), filetype="pdf") as pdf:
                if not pdf.is_pdf or pdf.page_count < 1:
                    raise InvalidUpload("PDF contains no pages")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(stream) as image:
                    actual = Image.MIME.get(image.format)
                    if actual != expected:
                        raise InvalidUpload("File content does not match its extension")
                    image.verify()
    except InvalidUpload:
        raise
    except (
        ValueError,
        RuntimeError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise InvalidUpload("File is not a readable PDF, image or UTF-8 text document") from error
    finally:
        stream.seek(0)
    return expected

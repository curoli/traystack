"""Stable NFC + whitespace + casefold rules. No hyphenation or punctuation removal."""

import re
import unicodedata

NORMALIZATION_VERSION = "nfc-whitespace-casefold-v1"


def normalize_for_search(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip().casefold()

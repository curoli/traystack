import pytest

from traystack.services.normalization import normalize_for_search
from traystack.services.text_extraction import (
    ExtractedPage,
    Extraction,
    assess_page,
    build_canonical_text,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The receiving\r\n party\t SHALL NOT disclose", "the receiving party shall not disclose"),
        ("  Cafe\u0301 STRASSE Straße  ", "café strasse strasse"),
        ("Pay 50,000; shall not pay 500,000.", "pay 50,000; shall not pay 500,000."),
        ("confiden-\ntial", "confiden- tial"),
        ("\n\f\t", ""),
    ],
)
def test_documented_normalization_preserves_significant_content(text, expected):
    assert normalize_for_search(text) == expected


def test_page_offsets_are_offsets_in_the_exact_saved_normalized_text():
    pages = [
        ExtractedPage(1, "Straße SHALL\n", "embedded_pdf_text"),
        ExtractedPage(2, "", "ocr", status="unavailable", quality_status="needs_review"),
        ExtractedPage(3, "not disclose 50,000.", "embedded_pdf_text"),
    ]
    result = build_canonical_text(Extraction(pages, {}))
    assert result.normalized_text == "strasse shall not disclose 50,000."
    assert result.normalized_text == normalize_for_search(result.plain_text)
    assert result.status == "partial"
    assert result.quality_status == "needs_review"
    assert result.pages_processed == 2
    for page in pages:
        assert result.normalized_text[page.start_offset : page.end_offset] == page.normalized_text


def test_manual_review_does_not_change_successful_page_coverage():
    page = assess_page(
        ExtractedPage(1, "The receiving party shall not disclose", "ocr", confidence=99), True
    )
    assert page.status == "complete"
    assert page.quality_status == "needs_review"
    assert "manual_review_requested" in page.quality_warnings


def test_no_text_and_replacement_characters_are_flagged():
    empty = assess_page(ExtractedPage(1, "", "ocr"), False)
    assert empty.status == "unavailable" and empty.quality_status == "needs_review"
    suspect = assess_page(
        ExtractedPage(1, "Long contract text with a \x00 missing glyph", "embedded_pdf_text"), False
    )
    assert "\x00" not in suspect.text and "\ufffd" in suspect.text
    assert suspect.quality_status == "needs_review"


def test_unassessed_page_prevents_no_known_issue_summary():
    result = build_canonical_text(
        Extraction(
            [ExtractedPage(1, "Some contract wording", "ocr", quality_status="unassessed")], {}
        )
    )
    assert result.status == "complete"
    assert result.quality_status == "unassessed"

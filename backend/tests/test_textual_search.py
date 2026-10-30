from uuid import uuid4

import pytest
from sqlalchemy import delete, event, update
from test_search import indexed

from traystack.models import PageText, ProcessingJob, Revision, RevisionText
from traystack.services import textual_search
from traystack.services.normalization import NORMALIZATION_VERSION
from traystack.services.textual_matching import WorkBudget, find_passages, text_differences


def search(client, query="confidential information", **options):
    response = client.post("/api/search/textual", json={"query": query, **options})
    assert response.status_code == 200, response.text
    return response.json()


def test_character_score_and_full_text_literal_search():
    query = "confidential information"
    text = "Header. confidentlal information. Footer. " + query + "! " + query
    passages = find_passages(text, query, 85, WorkBudget())
    assert sum(item.score == 100 for item in passages) == 2
    fuzzy = next(item for item in passages if item.score < 100)
    assert text[fuzzy.start : fuzzy.end] == "confidentlal information."
    # One substituted letter plus one added period in a 25-character passage.
    assert fuzzy.score == pytest.approx(92.0)
    assert len(find_passages(text, query, 100, WorkBudget())) == 2
    assert find_passages("prefixNEEDLEsuffix", "NEEDLE", 100, WorkBudget())[0].start == 6


@pytest.mark.parametrize("minimum", [0, -1, float("nan"), float("inf")])
def test_matcher_rejects_disabled_or_invalid_thresholds(minimum):
    with pytest.raises(ValueError):
        find_passages("x", "target", minimum, WorkBudget())


def test_short_documents_can_still_match_at_a_positive_threshold():
    assert find_passages("short", "short phrase", 30, WorkBudget())
    assert find_passages("x", "A much longer query with many words", 99, WorkBudget()) == []


@pytest.mark.parametrize(
    "query,passage,change",
    [
        ("shall not disclose information", "shall disclose information", "not"),
        ("Liability is limited to 50,000 euros", "Liability is limited to 500,000 euros", "500"),
        ("Payment is due in 30 days", "Payment is due in 90 days", "90"),
    ],
)
def test_material_differences_survive_high_similarity(query, passage, change):
    matches = find_passages(passage, query, 70, WorkBudget())
    assert matches and matches[0].score < 100
    diff = text_differences(query, passage)
    assert "".join(part.query_text for part in diff) == query
    assert "".join(part.passage_text for part in diff) == passage
    assert change in "".join(
        part.query_text + part.passage_text for part in diff if part.kind != "equal"
    )


@pytest.mark.integration
def test_multiple_occurrences_paging_unicode_page_spans_and_threshold(client):
    fixture = indexed(client, "Multiple", ["😀 Straße target", "Straße target. Straße target"])
    response = search(client, "STRASSE target", minimum_score=100, occurrence_limit=1)
    group = response["results"][0]
    assert group["occurrence_total"] == 3
    occurrence = group["occurrences"][0]
    assert occurrence["start_offset"] == 2 and occurrence["score"] == 100
    assert occurrence["matched_text"] == "strasse target" and occurrence["page_numbers"] == [1]
    next_page = search(
        client,
        "STRASSE target",
        minimum_score=100,
        document_id=str(fixture["document_id"]),
        occurrence_limit=1,
        occurrence_offset=1,
    )
    assert next_page["results"][0]["occurrences"][0]["page_numbers"] == [2]
    assert next_page["results"][0]["occurrences"][0]["occurrence_id"] != occurrence["occurrence_id"]
    assert search(client, "STRASSE target", mode="exact", minimum_score=100)["total"] == 0
    across = search(client, "target strasse", minimum_score=100)["results"][0]["occurrences"][0]
    assert across["page_numbers"] == [1, 2]
    raw = search(client, "target\n\f\nStraße", mode="exact", minimum_score=100)["results"][0][
        "occurrences"
    ][0]
    assert raw["page_numbers"] == [1, 2]


@pytest.mark.integration
def test_review_partial_sources_and_latest_scope_remain_honest(client):
    partial = indexed(
        client,
        "Review",
        ["confidentlal information", ""],
        quality="needs_review",
        failed_pages=(2,),
        manual=True,
    )
    old = indexed(client, "New revision", ["confidential information"])
    with client.app.state.session_factory.begin() as session:
        session.add(Revision(document_id=old["document_id"], revision_number=2))
    indexed(client, "Unsupported", ["confidential information"], version="future-v99")
    response = search(client, minimum_score=85)
    assert response["total"] == 1
    doc = response["results"][0]["document"]
    assert doc["document_id"] == str(partial["document_id"])
    assert doc["coverage"] == "partial" and "manual_review_requested" in doc["warnings"]
    assert response["unsearchable_total"] == 2
    assert response["summary"]["documents_searched"] == 1
    assert all("status" not in row for row in response["unsearchable"])
    assert search(client, minimum_score=100)["summary"]["documents_without_matches"] == 1
    # The literal absence API must still exclude the review source and latest unprocessed revision.
    absence = client.post("/api/search", json={"query": "missing", "relation": "lacks"}).json()
    assert absence["total"] == 0 and absence["unverifiable_total"] == 3


@pytest.mark.integration
def test_global_counts_independent_document_and_unsearchable_paging(client):
    for i in range(3):
        indexed(client, str(i), ["confidential information"])
    for i in range(2):
        indexed(client, f"Future {i}", ["confidential information"], version="future")
    first = search(client, minimum_score=100, limit=1, unsearchable_limit=1)
    second = search(
        client, minimum_score=100, limit=1, offset=1, unsearchable_limit=1, unsearchable_offset=1
    )
    assert first["summary"] == second["summary"]
    assert first["total"] == 3 and first["unsearchable_total"] == 2
    assert (
        first["results"][0]["document"]["document_id"]
        != second["results"][0]["document"]["document_id"]
    )
    assert first["unsearchable"][0]["document_id"] != second["unsearchable"][0]["document_id"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "options",
    [
        {"minimum_score": -1},
        {"minimum_score": 0},
        {"minimum_score": 101},
        {"minimum_score": "NaN"},
        {"minimum_score": "Infinity"},
        {"relation": "lacks"},
        {"scope": "all"},
        {"query": " "},
        {"query": "x" * 501},
        {"occurrence_offset": 1},
        {"occurrence_limit": 0},
        {"unsearchable_offset": -1},
        {"threshold": 80},
    ],
)
def test_invalid_textual_requests(client, options):
    assert (
        client.post("/api/search/textual", json={"query": "target", **options}).status_code == 422
    )


@pytest.mark.integration
def test_query_dependent_warnings_and_empty_library(client):
    assert search(client)["summary"]["documents_total"] == 0
    result = search(client, "A much longer query with several words", minimum_score=50)
    assert "large_edit_budget" in result["warnings"]
    assert "short_query" in search(client, "abc")["warnings"]


@pytest.mark.integration
def test_work_budget_rejects_entire_search_instead_of_truncating(client, monkeypatch):
    indexed(client, "Target", ["confidential information"])
    monkeypatch.setattr(textual_search, "WorkBudget", lambda: WorkBudget(characters=1))
    result = client.post("/api/search/textual", json={"query": "confidential information"})
    assert result.status_code == 422
    assert result.json()["detail"]["reason"] == "work_limit"
    assert result.json()["detail"]["results_complete"] is False


@pytest.mark.integration
def test_textual_snapshot_cannot_mix_old_text_with_new_pages(client, engine):
    fixture = indexed(client, "Snapshot", ["Background", "confidentlal information in old page"])
    replacement_id = uuid4()
    with client.app.state.session_factory.begin() as session:
        session.add(
            ProcessingJob(
                id=replacement_id,
                revision_id=fixture["revision_id"],
                source_artifact_id=fixture["artifact_id"],
                status="running",
                normalization_version=NORMALIZATION_VERSION,
                parameters={},
            )
        )
    app_engine = client.app.state.session_factory.kw["bind"]
    published = False

    def publish(connection, cursor, statement, parameters, context, executemany):
        nonlocal published
        if published or "FROM documents" not in statement or "strpos(" not in statement:
            return
        published = True
        with engine.begin() as writer:
            writer.execute(
                update(RevisionText)
                .where(RevisionText.revision_id == fixture["revision_id"])
                .values(
                    processing_job_id=replacement_id,
                    plain_text="New text",
                    normalized_text="new text",
                    pages_total=1,
                    pages_processed=1,
                    pages_failed=0,
                )
            )
            writer.execute(delete(PageText).where(PageText.revision_id == fixture["revision_id"]))
            writer.execute(
                PageText.__table__.insert().values(
                    revision_id=fixture["revision_id"],
                    page_number=1,
                    text="New text",
                    normalized_text="new text",
                    start_offset=0,
                    end_offset=8,
                    extraction_method="embedded_pdf_text",
                    status="complete",
                    quality_status="no_known_issue",
                    quality_warnings=[],
                    layout_metadata={},
                )
            )
            writer.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == replacement_id)
                .values(status="completed")
            )

    event.listen(app_engine, "after_cursor_execute", publish)
    try:
        result = search(client)
    finally:
        event.remove(app_engine, "after_cursor_execute", publish)
    assert published
    group = result["results"][0]
    assert group["document"]["processing_job_id"] == str(fixture["job_id"])
    assert group["occurrences"][0]["page_numbers"] == [2]
    assert "old page" in group["occurrences"][0]["snippet"]
    assert search(client)["total"] == 0


@pytest.mark.integration
def test_zero_length_page_does_not_claim_a_source_location(client):
    indexed(client, "Gap", ["first target", "", "ending text"], failed_pages=(2,))
    occurrence = search(client, "target ending", minimum_score=100)["results"][0]["occurrences"][0]
    assert occurrence["page_numbers"] == [1, 3]


def test_evaluation_uses_recovered_source_literals_and_reports_counterexamples():
    import runpy
    from pathlib import Path

    evaluate = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/evaluate_textual_search.py")
    )["evaluate"]
    rows = [
        {
            "id": "ocr",
            "query": "confidential information",
            "text": "confidentlal information",
            "literal": True,
            "case": "exact",
        },
        {
            "id": "changed",
            "query": "Liability is limited to 50,000 euros",
            "text": "Liability is limited to 500,000 euros",
            "literal": False,
            "case": "counterexample",
        },
    ]
    broad, strict = evaluate(rows, [85, 100])
    assert broad["source_literal_recovered"] == 1
    assert broad["material_counterexamples_returned"] == 1
    assert strict["source_literal_missed"] == 1
    assert strict["material_counterexamples_returned"] == 0


@pytest.mark.integration
@pytest.mark.ocr
def test_real_image_ocr_is_used_for_textual_candidates_without_transcription(client):
    from pathlib import Path

    sample = (
        Path(__file__).resolve().parents[2]
        / "examples/synthetic-handwriting/samples/clause-01-exact-clear.jpg"
    )
    uploaded = client.post(
        "/api/documents/upload",
        data={
            "title": "Real OCR candidate",
            "requires_manual_review": "true",
        },
        files={"file": (sample.name, sample.read_bytes())},
    )
    assert uploaded.status_code == 201
    revision = uploaded.json()["revisions"][0]
    client.post(f"/api/revisions/{revision['id']}/process", json={})
    from traystack.services.processing import run_once

    assert run_once(client.app.state.session_factory, client.app.state.storage)
    extracted = client.get(f"/api/revisions/{revision['id']}/text").json()
    assert extracted["pages"][0]["extraction_method"] == "ocr"
    result = search(
        client, "The receiving party shall not disclose confidential information.", minimum_score=85
    )
    group = result["results"][0]
    assert group["document"]["quality_status"] == "needs_review"
    assert "manual_review_requested" in group["document"]["warnings"]
    occurrence = group["occurrences"][0]
    assert (
        occurrence["matched_text"]
        == extracted["normalized_text"][occurrence["start_offset"] : occurrence["end_offset"]]
    )
    assert occurrence["page_numbers"] == [1]


def test_permissive_threshold_does_not_store_every_redundant_window():
    content = " ".join(f"background{index}" for index in range(50))
    # Hundreds of overlapping windows, but only one best window per word start.
    passages = find_passages(
        content,
        "a query with several entirely different target words",
        1,
        WorkBudget(matches=100),
    )
    assert passages and all(0 <= item.score <= 100 for item in passages)

"""Controlled canonical-text fixtures plus real upload/worker/search integration."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pymupdf
import pytest
from sqlalchemy import delete, event, update

from traystack.models import Artifact, Document, PageText, ProcessingJob, Revision, RevisionText
from traystack.services.normalization import NORMALIZATION_VERSION, normalize_for_search
from traystack.services.processing import run_once
from traystack.services.text_extraction import ExtractedPage, Extraction, build_canonical_text

pytestmark = pytest.mark.integration
FIXTURES = Path(__file__).resolve().parents[2] / "examples" / "synthetic-contracts"
PHRASE = "The receiving party shall not disclose confidential information"


def indexed(
    client,
    title,
    texts,
    *,
    quality="no_known_issue",
    failed_pages=(),
    manual=False,
    version=NORMALIZATION_VERSION,
    document_id=None,
    revision_number=1,
):
    """Store explicit synthetic extraction ground truth; real extraction is tested below."""
    with pymupdf.open() as pdf:
        for content in texts:
            page = pdf.new_page()
            page.insert_text((50, 60), content or "Synthetic empty-page fixture")
        data = pdf.tobytes()
    blob = client.app.state.storage.put_bytes(data, "application/pdf")
    result = build_canonical_text(
        Extraction(
            [
                ExtractedPage(
                    i + 1,
                    content,
                    "embedded_pdf_text",
                    status="unavailable" if i + 1 in failed_pages else "complete",
                    quality_status="needs_review" if i + 1 in failed_pages else quality,
                    quality_warnings=["no_text_detected"] if i + 1 in failed_pages else [],
                )
                for i, content in enumerate(texts)
            ],
            {"test_fixture": "controlled canonical extraction"},
        )
    )
    with client.app.state.session_factory.begin() as session:
        document = session.get(Document, document_id) if document_id else Document(title=title)
        revision = Revision(document=document, revision_number=revision_number)
        artifact = Artifact(
            revision=revision,
            kind="original",
            mime_type="application/pdf",
            original_filename="synthetic.pdf",
            storage_key=blob.storage_key,
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            processor="upload",
            parameters={"requires_manual_review": manual},
        )
        session.add_all([document, revision, artifact])
        session.flush()
        job = ProcessingJob(
            revision_id=revision.id,
            source_artifact_id=artifact.id,
            status="completed",
            attempts=1,
            normalization_version=version,
            parameters={"requires_manual_review": manual},
            processor_versions={"fixture": "controlled"},
            finished_at=datetime.now(UTC),
        )
        session.add(job)
        session.flush()
        index = RevisionText(
            revision_id=revision.id,
            source_artifact_id=artifact.id,
            processing_job_id=job.id,
            normalization_version=version,
            plain_text=result.plain_text,
            normalized_text=result.normalized_text,
            status=result.status,
            quality_status=result.quality_status,
            quality_warnings=result.quality_warnings,
            pages_total=len(texts),
            pages_processed=result.pages_processed,
            pages_failed=len(texts) - result.pages_processed,
        )
        session.add(index)
        session.flush()
        session.add_all(
            PageText(
                revision_id=revision.id,
                **{
                    key: getattr(page, key)
                    for key in [
                        "page_number",
                        "text",
                        "normalized_text",
                        "start_offset",
                        "end_offset",
                        "extraction_method",
                        "status",
                        "quality_status",
                        "quality_warnings",
                        "confidence",
                        "layout_metadata",
                    ]
                },
            )
            for page in result.pages
        )
        return {
            "document_id": document.id,
            "revision_id": revision.id,
            "artifact_id": artifact.id,
            "job_id": job.id,
        }


def search(client, query="target", **options):
    response = client.post("/api/search", json={"query": query, **options})
    assert response.status_code == 200, response.text
    return response.json()


def test_real_upload_worker_search_and_retrieve(client):
    for filename in [
        "A-confidentiality.pdf",
        "D-delivery.pdf",
        "P-printed-scan.jpg",
        "E-difficult-scan.jpg",
    ]:
        uploaded = client.post(
            "/api/documents/upload",
            data={"title": filename, "requires_manual_review": filename.startswith("E")},
            files={"file": (filename, (FIXTURES / filename).read_bytes())},
        )
        assert uploaded.status_code == 201
        revision_id = uploaded.json()["revisions"][0]["id"]
        assert client.post(f"/api/revisions/{revision_id}/process", json={}).status_code == 202
        assert run_once(client.app.state.session_factory, client.app.state.storage)
    positive = search(client, PHRASE)
    assert {row["title"] for row in positive["results"]} == {
        "A-confidentiality.pdf",
        "P-printed-scan.jpg",
    }
    assert positive["summary"] == {
        "documents_total": 4,
        "found": 2,
        "not_found_in_processed_text": 1,
        "unverifiable": 1,
    }
    negative = search(client, PHRASE, relation="lacks")
    assert [row["title"] for row in negative["results"]] == ["D-delivery.pdf"]
    assert [row["title"] for row in negative["unverifiable"]] == ["E-difficult-scan.jpg"]
    for row in positive["results"]:
        assert row["artifact_id"] and row["processing_job_id"] and row["processor_versions"]
        assert row["page_number"] == 1 and row["score"] is None
        assert row["matched_text"] == normalize_for_search(PHRASE)
        assert (
            client.get(f"/api/artifacts/{row['artifact_id']}/content").content
            == (FIXTURES / row["title"]).read_bytes()
        )


@pytest.mark.parametrize(
    "mode,query,expected",
    [
        ("exact", "Alpha SHALL NOT\r\ndisclose.", "found"),
        ("exact", "alpha shall not disclose.", "not_found_in_processed_text"),
        ("exact", "Alpha SHALL NOT disclose.", "not_found_in_processed_text"),
        ("normalized", "  ALPHA shall\t NOT disclose. ", "found"),
    ],
)
def test_exact_is_literal_and_normalized_uses_saved_rules(client, mode, query, expected):
    indexed(client, "Whitespace", ["Alpha SHALL NOT\r\ndisclose."])
    response = search(
        client, query, mode=mode, relation="contains" if expected == "found" else "lacks"
    )
    assert response["results"][0]["status"] == expected


@pytest.mark.parametrize(
    "mode,query",
    [
        ("normalized", "STRASSE SHALL\nnot disclose"),
        ("exact", "Straße SHALL\n\f\nnot disclose"),
    ],
)
def test_cross_page_matches_have_correct_unicode_offsets_and_page_span(client, mode, query):
    texts = ["Intro Straße SHALL", "not disclose 50,000."]
    indexed(client, "Across pages", texts)
    result = search(client, query, mode=mode)["results"][0]
    canonical = "\n\f\n".join(texts)
    if mode == "normalized":
        canonical = normalize_for_search(canonical)
    assert canonical[result["start_offset"] : result["end_offset"]] == result["matched_text"]
    assert result["page_numbers"] == [1, 2]
    assert result["page_number"] == 1 and result["end_page_number"] == 2
    relative = result["start_offset"] - result["snippet_start_offset"]
    assert (
        result["snippet"][relative : relative + len(result["matched_text"])]
        == result["matched_text"]
    )


@pytest.mark.parametrize("query", ["%", "_", "\\", "' OR 1=1 --", "50,000", "shall not"])
def test_wildcards_punctuation_and_sql_text_are_literal(client, query):
    indexed(client, "Containing", ["prefix " + query + " suffix"])
    indexed(client, "Different", ["A different contract, 500,000, shall disclose."])
    response = search(client, query)
    assert [row["title"] for row in response["results"]] == ["Containing"]
    assert client.get("/api/documents").json()["total"] == 2


@pytest.mark.parametrize("quality", ["needs_review", "unassessed"])
def test_complete_but_uncertain_text_is_never_a_negative_match(client, quality):
    indexed(client, "Uncertain", ["Other contract wording"], quality=quality)
    result = search(client, relation="lacks")
    assert not result["results"] and result["unverifiable_total"] == 1
    assert result["unverifiable"][0]["coverage"] == "complete"


def test_positive_partial_or_review_required_text_keeps_warnings(client):
    indexed(client, "Partial positive", ["target appears", ""], failed_pages=(2,), manual=True)
    result = search(client)["results"][0]
    assert result["status"] == "found" and result["coverage"] == "partial"
    assert "manual_review_requested" in result["warnings"]
    negative = search(client, "missing", relation="lacks")
    assert not negative["results"] and negative["unverifiable_total"] == 1


def test_latest_revision_never_falls_back_to_older_processed_text(client):
    first = indexed(client, "Latest negative", ["target appears in old revision"])
    indexed(
        client,
        "unused",
        ["New wording without the phrase"],
        document_id=first["document_id"],
        revision_number=2,
    )
    second = indexed(client, "Latest unprocessed", ["target also in old revision"])
    with client.app.state.session_factory.begin() as session:
        session.add(Revision(document_id=second["document_id"], revision_number=2))
        session.add(Document(title="No revision yet"))
    response = search(client, relation="lacks")
    assert [(row["title"], row["revision_number"]) for row in response["results"]] == [
        ("Latest negative", 2)
    ]
    assert {row["title"] for row in response["unverifiable"]} == {
        "Latest unprocessed",
        "No revision yet",
    }
    assert response["summary"]["found"] == 0
    assert (
        next(row for row in response["unverifiable"] if row["title"] == "No revision yet")[
            "revision_id"
        ]
        is None
    )


def test_failed_reprocessing_preserves_selected_text_with_visible_warning(client):
    fixture = indexed(client, "Existing index", ["Existing wording"])
    response = client.post(f"/api/revisions/{fixture['revision_id']}/process", json={})
    job_id = UUID(response.json()["id"])
    with client.app.state.session_factory.begin() as session:
        job = session.get(ProcessingJob, job_id)
        job.status, job.error_message = "failed", "processing_failed"
    result = search(client, "missing", relation="lacks")["results"][0]
    assert result["processing_job_id"] == str(fixture["job_id"])
    assert result["latest_job"]["id"] == str(job_id)
    assert result["latest_job"]["error_message"] == "processing_failed"
    assert "newer_run_failed" in result["warnings"]


def test_later_manual_review_requirement_prevents_negative_use_of_older_clean_index(client):
    fixture = indexed(client, "Review added later", ["Other wording"])
    response = client.post(
        f"/api/revisions/{fixture['revision_id']}/process", json={"requires_manual_review": True}
    )
    assert response.status_code == 202
    response = search(client, relation="lacks")
    assert not response["results"]
    assert response["unverifiable"][0]["quality_status"] == "no_known_issue"
    assert "manual_review_requested" in response["unverifiable"][0]["warnings"]
    assert "newer_run_pending" in response["unverifiable"][0]["warnings"]


def test_unknown_normalization_version_is_unverifiable_but_exact_remains_literal(client):
    indexed(client, "Future rules", ["target appears"], version="unknown-v99")
    response = search(client)
    assert not response["results"]
    assert "unsupported_normalization_version" in response["unverifiable"][0]["warnings"]
    assert search(client, mode="exact")["results"][0]["status"] == "found"


def test_pagination_keeps_global_counts_and_unknown_results_independent(client):
    for i in range(4):
        indexed(client, f"Found {i}", ["target here"])
        indexed(client, f"Negative {i}", ["Other wording"])
        indexed(client, f"Unknown {i}", ["Other wording"], quality="unassessed")
    first = search(client, relation="lacks", limit=2, unverifiable_limit=1)
    second = search(
        client, relation="lacks", limit=2, offset=2, unverifiable_limit=1, unverifiable_offset=1
    )
    assert (
        first["summary"]
        == second["summary"]
        == {"documents_total": 12, "found": 4, "not_found_in_processed_text": 4, "unverifiable": 4}
    )
    assert first["total"] == second["total"] == first["unverifiable_total"] == 4
    assert len(first["results"]) == 2 and len(first["unverifiable"]) == 1
    assert {row["document_id"] for row in first["results"]}.isdisjoint(
        row["document_id"] for row in second["results"]
    )
    assert first["unverifiable"][0]["document_id"] != second["unverifiable"][0]["document_id"]
    assert all(row["snippet"] is None and row["start_offset"] is None for row in first["results"])


@pytest.mark.parametrize(
    "options",
    [
        {"query": ""},
        {"query": "  \n"},
        {"query": "bad\x00text"},
        {"query": "\ud800"},
        {"query": "a" * 2001},
        {"mode": "fuzzy"},
        {"relation": "invalid"},
        {"scope": "all"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"unverifiable_limit": 0},
        {"unverifiable_offset": -1},
        {"threshold": 0.8},
    ],
)
def test_search_validation(client, options):
    response = client.post(
        "/api/search",
        content=json.dumps({"query": "target", **options}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_empty_library_has_explicit_zero_counts(client):
    result = search(client, relation="lacks")
    assert (
        result["total"] == result["unverifiable_total"] == result["summary"]["documents_total"] == 0
    )
    assert result["results"] == result["unverifiable"] == []


def test_counts_snippets_and_page_locations_use_one_snapshot_during_publication(client, engine):
    fixture = indexed(client, "Snapshot", ["First page wording", "target in old second page"])
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        replacement = ProcessingJob(
            revision_id=fixture["revision_id"],
            source_artifact_id=fixture["artifact_id"],
            status="running",
            attempts=1,
            normalization_version=NORMALIZATION_VERSION,
            parameters={},
        )
        session.add(replacement)
        session.flush()
        replacement_id = replacement.id
    app_engine = sessions.kw["bind"]
    published = False

    def publish_between_search_queries(
        connection, cursor, statement, parameters, context, executemany
    ):
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
                    plain_text="New content",
                    normalized_text="new content",
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
                    text="New content",
                    normalized_text="new content",
                    start_offset=0,
                    end_offset=11,
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

    event.listen(app_engine, "after_cursor_execute", publish_between_search_queries)
    try:
        response = search(client)
    finally:
        event.remove(app_engine, "after_cursor_execute", publish_between_search_queries)
    assert published
    assert response["summary"]["found"] == 1
    result = response["results"][0]
    assert result["processing_job_id"] == str(fixture["job_id"])
    assert "target in old second page" in result["snippet"]
    assert result["page_numbers"] == [2]
    assert search(client)["summary"]["found"] == 0


def test_initial_pending_or_failed_job_does_not_claim_a_previous_selected_text(client):
    response = client.post(
        "/api/documents/upload",
        data={"title": "First processing"},
        files={"file": ("contract.pdf", (FIXTURES / "A-confidentiality.pdf").read_bytes())},
    )
    revision = response.json()["revisions"][0]
    assert client.post(f"/api/revisions/{revision['id']}/process", json={}).status_code == 202
    pending = search(client, relation="lacks")["unverifiable"][0]
    assert (
        "processing_pending" in pending["warnings"]
        and "newer_run_pending" not in pending["warnings"]
    )
    assert pending["processing_job_id"] is None
    for file in client.app.state.storage.root.glob("*/*/*"):
        file.unlink()
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    failed = search(client, relation="lacks")["unverifiable"][0]
    assert (
        "processing_failed" in failed["warnings"] and "newer_run_failed" not in failed["warnings"]
    )
    assert failed["processing_job_id"] is None


def test_late_repeated_phrase_is_found_and_never_classified_as_absent(client):
    pages = ["Background paragraph.\n" * 30] * 6 + [
        "The target appears here; target appears again."
    ]
    indexed(client, "Late clause", pages)
    result = search(client, "target")
    assert result["total"] == 1
    hit = result["results"][0]
    assert hit["start_offset"] > 3500 and hit["page_number"] == 7
    assert hit["start_offset"] == normalize_for_search("\n\f\n".join(pages)).index("target")
    assert len(hit["snippet"]) <= len("target") + 160
    absence = search(client, "target", relation="lacks")
    assert absence["results"] == [] and absence["summary"]["found"] == 1

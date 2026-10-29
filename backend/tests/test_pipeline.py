import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pymupdf
import pytest
from sqlalchemy import text

from traystack.models import Artifact
from traystack.services import processing, text_extraction
from traystack.worker import recover_running

FIXTURES = Path(__file__).resolve().parents[2] / "examples" / "synthetic-contracts"
PHRASE = "the receiving party shall not disclose confidential information"
pytestmark = pytest.mark.integration


def upload(client, filename="A-confidentiality.pdf", manual=False):
    response = client.post(
        "/api/documents/upload",
        data={
            "title": "Pipeline fixture",
            "requires_manual_review": str(manual).lower(),
        },
        files={"file": (filename, (FIXTURES / filename).read_bytes())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def enqueue(client, document, **payload):
    revision = document["revisions"][0]
    response = client.post(
        f"/api/revisions/{revision['id']}/process",
        json={
            "source_artifact_id": revision["artifacts"][0]["id"],
            **payload,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def run_worker(client):
    return processing.run_once(client.app.state.session_factory, client.app.state.storage)


def selected_text(client, document):
    response = client.get(f"/api/revisions/{document['revisions'][0]['id']}/text")
    assert response.status_code == 200, response.text
    return response.json()


def test_pdf_processing_provenance_real_derivatives_and_original_bytes(client):
    document = upload(client)
    job = enqueue(client, document)
    assert job["status"] == "queued" and job["attempts"] == 0
    assert run_worker(client)
    assert not run_worker(client)
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "completed" and job["attempts"] == 1
    assert job["processor_versions"]["pymupdf"] == pymupdf.VersionBind
    assert job["started_at"] and job["finished_at"] and len(job["result_artifact_ids"]) == 2
    index = selected_text(client, document)
    assert index["processing_job_id"] == job["id"]
    assert PHRASE in index["normalized_text"]
    assert index["status"] == "complete" and index["quality_status"] == "no_known_issue"
    assert index["pages_total"] == index["pages_processed"] == 1
    assert index["pages"][0]["extraction_method"] == "embedded_pdf_text"
    assert index["pages"][0]["confidence"] is None
    assert index["pages"][0]["layout_metadata"]["words"]
    fresh = client.get(f"/api/documents/{document['id']}").json()
    revision = fresh["revisions"][0]
    assert "plain_text" not in revision["text_index"]
    assert "normalized_text" not in json.dumps(fresh)
    assert revision["processing_status"] == "completed"
    artifacts = {artifact["kind"]: artifact for artifact in revision["artifacts"]}
    assert set(artifacts) == {"original", "structured_json", "extracted_markdown"}
    for kind in ["structured_json", "extracted_markdown"]:
        artifact = artifacts[kind]
        assert artifact["source_artifact_id"] == artifacts["original"]["id"]
        assert artifact["parameters"]["processing_job_id"] == job["id"]
        content = client.get(f"/api/artifacts/{artifact['id']}/content").content
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
        if kind == "structured_json":
            result = json.loads(content)
            assert result["processing_job_id"] == job["id"]
            assert result["pages"][0]["text"] == index["pages"][0]["text"]
        else:
            assert b"## Page 1" in content and b"shall not disclose" in content
    assert (
        client.get(f"/api/artifacts/{artifacts['original']['id']}/content").content
        == (FIXTURES / "A-confidentiality.pdf").read_bytes()
    )


@pytest.mark.ocr
def test_printed_jpeg_uses_real_tesseract(client):
    document = upload(client, "P-printed-scan.jpg")
    enqueue(client, document)
    assert run_worker(client)
    index = selected_text(client, document)
    assert index["status"] == "complete"
    assert PHRASE in index["normalized_text"]
    page = index["pages"][0]
    assert page["extraction_method"] == "ocr"
    assert 0 <= page["confidence"] <= 100
    assert page["layout_metadata"]["words"]
    assert index["quality_status"] == "no_known_issue"


@pytest.mark.ocr
@pytest.mark.parametrize("filename", ["P-printed-scan.jpg", "E-difficult-scan.jpg"])
def test_manual_flag_survives_actual_ocr(client, filename):
    document = upload(client, filename, manual=True)
    enqueue(client, document, requires_manual_review=False)
    run_worker(client)
    index = selected_text(client, document)
    assert index["quality_status"] == "needs_review"
    assert "manual_review_requested" in index["quality_warnings"]
    if filename.startswith("P"):
        assert index["status"] == "complete"  # Independent from the quality verdict.


@pytest.fixture
def mixed_pdf():
    with pymupdf.open() as document:
        with pymupdf.open(FIXTURES / "D-delivery.pdf") as digital:
            document.insert_pdf(digital)
        page = document.new_page(width=595, height=842)
        page.insert_text((50, 30), "Embedded header beside scanned contract body", fontsize=10)
        page.insert_image(
            pymupdf.Rect(0, 60, 595, 842), filename=str(FIXTURES / "P-printed-scan.jpg")
        )
        return document.tobytes()


def upload_bytes(client, data):
    response = client.post(
        "/api/documents/upload", data={"title": "Mixed pages"}, files={"file": ("mixed.pdf", data)}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.ocr
def test_mixed_pdf_extracts_each_page_without_ignoring_scan_beside_header(client, mixed_pdf):
    document = upload_bytes(client, mixed_pdf)
    enqueue(client, document)
    run_worker(client)
    index = selected_text(client, document)
    assert [page["extraction_method"] for page in index["pages"]] == ["embedded_pdf_text", "ocr"]
    assert PHRASE in index["pages"][1]["normalized_text"]
    assert index["pages_processed"] == 2
    for page in index["pages"]:
        assert (
            index["normalized_text"][page["start_offset"] : page["end_offset"]]
            == page["normalized_text"]
        )


def test_ocr_timeout_marks_partial_coverage_and_keeps_successful_page(
    client, mixed_pdf, monkeypatch
):
    def timeout(*args, **kwargs):
        raise RuntimeError("SECRET runtime diagnostic")

    monkeypatch.setattr(text_extraction.pytesseract, "image_to_data", timeout)
    document = upload_bytes(client, mixed_pdf)
    job = enqueue(client, document)
    run_worker(client)
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "completed"
    index = selected_text(client, document)
    assert index["status"] == "partial" and index["quality_status"] == "needs_review"
    assert index["pages_processed"] == index["pages_failed"] == 1
    assert "ocr_timeout" in index["quality_warnings"]
    assert "SECRET" not in json.dumps(index)


def test_engine_failure_is_not_mislabelled_as_timeout(client, monkeypatch):
    def failure(*args, **kwargs):
        raise text_extraction.pytesseract.TesseractError(1, "SECRET diagnostic")

    monkeypatch.setattr(text_extraction.pytesseract, "image_to_data", failure)
    document = upload(client, "P-printed-scan.jpg")
    enqueue(client, document)
    run_worker(client)
    index = selected_text(client, document)
    assert index["status"] == "unavailable"
    assert (
        "ocr_failed" in index["quality_warnings"] and "ocr_timeout" not in index["quality_warnings"]
    )


def test_empty_image_never_becomes_complete_empty_text(client, monkeypatch):
    monkeypatch.setattr(text_extraction.pytesseract, "image_to_data", lambda *a, **kw: {"text": []})
    document = upload(client, "P-printed-scan.jpg")
    enqueue(client, document)
    run_worker(client)
    index = selected_text(client, document)
    assert index["status"] == "unavailable" and index["quality_status"] == "needs_review"
    assert "no_text_detected" in index["quality_warnings"]


def test_failed_reprocessing_preserves_selected_run_and_retry_creates_new_run(
    client, monkeypatch, caplog
):
    document = upload(client)
    first = enqueue(client, document)
    run_worker(client)
    initial = selected_text(client, document)
    real_extract = processing.extract_source

    def fail(*args, **kwargs):
        raise ValueError("TOP SECRET contract content")

    monkeypatch.setattr(processing, "extract_source", fail)
    failed = enqueue(client, document)
    run_worker(client)
    failed = client.get(f"/api/jobs/{failed['id']}").json()
    assert failed["status"] == "failed" and failed["error_message"] == "processing_failed"
    assert "TOP SECRET" not in caplog.text
    assert selected_text(client, document) == initial
    detail = client.get(f"/api/documents/{document['id']}").json()["revisions"][0]
    assert detail["processing_status"] == "failed"
    assert detail["text_index"]["processing_job_id"] == first["id"]
    assert len(detail["artifacts"]) == 3
    monkeypatch.setattr(processing, "extract_source", real_extract)
    response = client.post(f"/api/jobs/{failed['id']}/retry")
    assert response.status_code == 202
    retry = response.json()
    assert retry["id"] != failed["id"] and retry["retry_of_job_id"] == failed["id"]
    assert retry["parameters"] == failed["parameters"]
    run_worker(client)
    assert client.get(f"/api/jobs/{failed['id']}").json() == failed
    assert selected_text(client, document)["processing_job_id"] == retry["id"]
    artifacts = client.get(f"/api/documents/{document['id']}").json()["revisions"][0]["artifacts"]
    assert len(artifacts) == 5  # Earlier immutable derivatives are retained.


def test_publication_failure_rolls_back_text_pages_and_artifacts(client, monkeypatch):
    document = upload(client)
    enqueue(client, document)
    run_worker(client)
    initial = selected_text(client, document)
    extract = processing.extract_source

    def invalid_result(*args, **kwargs):
        result = extract(*args, **kwargs)
        result.pages[0].start_offset = -1  # Force a database constraint failure during publish.
        return result

    monkeypatch.setattr(processing, "extract_source", invalid_result)
    failed = enqueue(client, document)
    run_worker(client)
    assert client.get(f"/api/jobs/{failed['id']}").json()["status"] == "failed"
    assert selected_text(client, document) == initial
    assert (
        len(client.get(f"/api/documents/{document['id']}").json()["revisions"][0]["artifacts"]) == 3
    )


def test_integrity_failure_and_retry_after_restoring_source(client):
    document = upload(client)
    artifact = document["revisions"][0]["artifacts"][0]
    sha = artifact["sha256"]
    path = client.app.state.storage.path_for(f"{sha[:2]}/{sha[2:4]}/{sha}")
    data = path.read_bytes()
    path.write_bytes(b"corrupt")
    job = enqueue(client, document)
    run_worker(client)
    failed = client.get(f"/api/jobs/{job['id']}").json()
    assert (
        failed["status"] == "failed" and failed["error_message"] == "source_integrity_check_failed"
    )
    assert client.get(f"/api/revisions/{document['revisions'][0]['id']}/text").status_code == 404
    path.write_bytes(data)
    retry = client.post(f"/api/jobs/{job['id']}/retry").json()
    run_worker(client)
    assert client.get(f"/api/jobs/{retry['id']}").json()["status"] == "completed"


def test_one_active_run_and_skip_locked_claiming(client, engine):
    document = upload(client)
    job = enqueue(client, document)
    revision_id = document["revisions"][0]["id"]
    assert client.post(f"/api/revisions/{revision_id}/process", json={}).status_code == 409
    sessions = client.app.state.session_factory
    with engine.begin() as connection:
        connection.execute(
            text("SELECT id FROM processing_jobs WHERE id=:id FOR UPDATE"), {"id": job["id"]}
        )
        assert processing.claim_next_job(sessions) is None
    assert processing.claim_next_job(sessions) == UUID(job["id"])
    assert processing.claim_next_job(sessions) is None
    assert client.post(f"/api/revisions/{revision_id}/process", json={}).status_code == 409


def test_two_workers_can_claim_a_queued_job_only_once(client):
    document = upload(client)
    job = enqueue(client, document)
    sessions = client.app.state.session_factory
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: processing.claim_next_job(sessions), range(2)))
    assert results.count(UUID(job["id"])) == 1 and results.count(None) == 1


def test_source_selection_retry_validation_and_unknown_objects(client):
    first, second = upload(client), upload(client)
    revision = first["revisions"][0]
    foreign = second["revisions"][0]["artifacts"][0]["id"]
    assert (
        client.post(
            f"/api/revisions/{revision['id']}/process", json={"source_artifact_id": foreign}
        ).status_code
        == 422
    )
    assert client.post(f"/api/revisions/{uuid4()}/process", json={}).status_code == 404
    assert client.get(f"/api/jobs/{uuid4()}").status_code == 404
    assert client.post(f"/api/jobs/{uuid4()}/retry").status_code == 404
    job = enqueue(client, first)
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 409
    run_worker(client)
    result = client.get(f"/api/jobs/{job['id']}").json()
    assert (
        client.post(
            f"/api/revisions/{revision['id']}/process",
            json={"source_artifact_id": result["result_artifact_ids"][0]},
        ).status_code
        == 422
    )


def test_multiple_originals_require_explicit_source_selection(client):
    document = upload(client)
    revision = document["revisions"][0]
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        source = session.get(Artifact, UUID(revision["artifacts"][0]["id"]))
        session.add(
            Artifact(
                revision_id=source.revision_id,
                kind="original",
                mime_type=source.mime_type,
                original_filename="alternative.pdf",
                storage_key=source.storage_key,
                sha256=source.sha256,
                size_bytes=source.size_bytes,
                processor="upload",
                parameters={},
            )
        )
    assert client.post(f"/api/revisions/{revision['id']}/process", json={}).status_code == 422
    assert enqueue(client, document)["source_artifact_id"] == revision["artifacts"][0]["id"]


def test_interrupted_run_recovery_blocks_old_publication(client):
    document = upload(client)
    job = enqueue(client, document)
    sessions = client.app.state.session_factory
    job_id = processing.claim_next_job(sessions)
    assert recover_running(sessions) == 1
    processing.execute_job(job_id, sessions, client.app.state.storage)
    assert client.get(f"/api/jobs/{job['id']}").json()["error_message"] == "worker_interrupted"
    assert client.get(f"/api/revisions/{document['revisions'][0]['id']}/text").status_code == 404
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 202
    assert run_worker(client)


def test_page_limit_fails_with_explicit_reason(client, mixed_pdf):
    client.app.state.settings.processing_max_pages = 1
    document = upload_bytes(client, mixed_pdf)
    job = enqueue(client, document)
    run_worker(client)
    result = client.get(f"/api/jobs/{job['id']}").json()
    assert result["status"] == "failed" and result["error_message"] == "source_page_limit_exceeded"


def test_explicit_run_review_flag_cannot_disappear_on_later_processing(client):
    document = upload(client)
    enqueue(client, document, requires_manual_review=True)
    run_worker(client)
    assert selected_text(client, document)["quality_status"] == "needs_review"
    later = enqueue(client, document, requires_manual_review=False)
    assert later["parameters"]["requires_manual_review"] is True
    run_worker(client)
    assert selected_text(client, document)["quality_status"] == "needs_review"


def test_retry_of_older_failed_run_inherits_later_manual_review_flag(client):
    document = upload(client)
    older = enqueue(client, document)
    sessions = client.app.state.session_factory
    processing.claim_next_job(sessions)
    recover_running(sessions)
    enqueue(client, document, requires_manual_review=True)
    run_worker(client)
    response = client.post(f"/api/jobs/{older['id']}/retry")
    assert response.status_code == 202
    assert response.json()["parameters"]["requires_manual_review"] is True
    assert (
        client.get(f"/api/jobs/{older['id']}").json()["parameters"]["requires_manual_review"]
        is False
    )
    run_worker(client)
    assert selected_text(client, document)["quality_status"] == "needs_review"


def test_multi_frame_image_is_not_silently_reduced_to_first_frame(client):
    from io import BytesIO

    from PIL import Image

    data = BytesIO()
    Image.new("RGB", (20, 20), "white").save(
        data,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (20, 20), "black")],
        duration=100,
        loop=0,
    )
    response = client.post(
        "/api/documents/upload",
        data={"title": "Multiple frames"},
        files={"file": ("frames.png", data.getvalue())},
    )
    assert response.status_code == 201
    job = enqueue(client, response.json())
    run_worker(client)
    result = client.get(f"/api/jobs/{job['id']}").json()
    assert (
        result["status"] == "failed" and result["error_message"] == "multi_frame_image_unsupported"
    )

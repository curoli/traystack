from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from test_reviews import command
from test_search import indexed

from traystack.models import ArchivedText, Document, SearchRun
from traystack.services import search_runs
from traystack.services.processing import run_once
from traystack.services.semantic import SemanticUnavailable

pytestmark = pytest.mark.integration


def create(client, **extra):
    response = client.post(
        "/api/search-runs",
        json={
            "name": "Contract review",
            "search": {"query": "target phrase", "minimum_score": 85, **extra},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_full_snapshot_survives_processing_metadata_and_library_changes(client, monkeypatch):
    original = indexed(client, "Original title", ["target phrase around " * 7])
    indexed(client, "No match", ["Completely unrelated shipping schedule"])
    client.post(
        "/api/documents/upload",
        files={"file": ("pending.txt", b"target phrase")},
        data={"title": "Pending"},
    )
    first = create(client, limit=1, occurrence_limit=1, unsearchable_limit=1)
    identity = first["run_id"]
    assert first["summary"]["occurrences_total"] == 7
    assert first["scope_total"] == 3 and first["unsearchable_total"] == 1
    page = client.get(
        f"/api/search-runs/{identity}",
        params={"document_id": str(original["document_id"]), "occurrence_offset": 5},
    )
    assert page.status_code == 200, page.text
    assert len(page.json()["results"][0]["occurrences"]) == 2
    source = client.get(f"/api/search-runs/{identity}/sources/{original['job_id']}")
    assert source.status_code == 200
    before = source.json()
    assert before["plain_text"].startswith("target phrase")
    with client.app.state.session_factory.begin() as session:
        session.execute(
            update(Document)
            .where(Document.id == original["document_id"])
            .values(title="Changed title")
        )
    indexed(client, "New document", ["target phrase around"])
    assert (
        client.post(f"/api/revisions/{original['revision_id']}/process", json={}).status_code == 202
    )
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    # No matching, model or current selected text is needed when opening or paging a run.
    monkeypatch.setattr(
        search_runs, "textual_snapshot", lambda *args, **kwargs: pytest.fail("Search reran")
    )
    reopened = client.get(f"/api/search-runs/{identity}").json()
    assert reopened["scope_total"] == 3 and reopened["summary"]["occurrences_total"] == 7
    assert reopened["searched_at"] == first["searched_at"]
    assert reopened["results"][0]["document"]["title"] == "Original title"
    assert client.get(f"/api/search-runs/{identity}/sources/{original['job_id']}").json() == before
    scope = client.get(f"/api/search-runs/{identity}/scope", params={"limit": 1}).json()
    assert scope["total"] == 3 and len(scope["items"]) == 1


def test_saved_reviews_remain_editable_after_reprocessing_and_live_reviews_stay_protected(client):
    source = indexed(client, "Reviewed", ["target phrase around"])
    run = create(client)
    payload = command(run)
    assert (
        client.post(f"/api/revisions/{source['revision_id']}/process", json={}).status_code == 202
    )
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    assert client.post("/api/reviews", json=payload).status_code == 409
    payload["search_run_id"] = run["run_id"]
    saved = client.post("/api/reviews", json=payload)
    assert saved.status_code == 200, saved.text
    again = client.get(f"/api/search-runs/{run['run_id']}").json()
    item = again["results"][0]["occurrences"][0]
    assert item["review"]["decision"] == "keep"
    assert item["review_at_capture"]["decision"] == "unreviewed"
    assert client.post("/api/reviews", json=payload).status_code == 409
    assert (
        client.post("/api/reviews", json={**payload, "matched_sha256": "a" * 64}).status_code == 409
    )
    fresh = create(client)
    assert fresh["review_counts"]["unreviewed"] == 1
    assert fresh["results"][0]["occurrences"][0]["occurrence_id"] != item["occurrence_id"]


def test_run_again_rename_list_and_zero_results_are_persistent(client):
    indexed(client, "One", ["target phrase around"])
    first = create(client)
    indexed(client, "Two", ["target phrase around"])
    response = client.post(
        "/api/search-runs",
        json={
            "parent_run_id": first["run_id"],
            "name": "Second review",
            "search": {"query": "target phrase", "minimum_score": 85},
        },
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["run_id"] != first["run_id"]
    assert second["parent_run_id"] == first["run_id"] and second["total"] == 2
    assert client.get(f"/api/search-runs/{first['run_id']}").json()["total"] == 1
    assert (
        client.post(
            f"/api/search-runs/{first['run_id']}/name", json={"name": "Renamed"}
        ).status_code
        == 200
    )
    listing = client.get("/api/search-runs", params={"limit": 1}).json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    assert client.get(f"/api/search-runs/{first['run_id']}").json()["run_name"] == "Renamed"
    empty = create(client, query="nonexistent expression")
    assert empty["total"] == 0 and empty["scope_total"] == 2
    assert client.get(f"/api/search-runs/{empty['run_id']}").json()["results"] == []


def test_failures_create_no_partial_run_or_source_archive(client, monkeypatch):
    indexed(client, "One", ["target phrase around"])
    client.app.state.settings.search_snapshot_max_bytes = 1
    error = client.post("/api/search-runs", json={"search": {"query": "target phrase"}})
    assert error.status_code == 422
    assert error.json()["detail"]["results_complete"] is False
    assert client.get("/api/search-runs").json()["total"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ArchivedText)) == 0
    client.app.state.settings.search_snapshot_max_bytes = 64_000_000
    # Ephemeral search still neither persists nor needs snapshot storage.
    assert client.post("/api/search/textual", json={"query": "target phrase"}).status_code == 200
    assert client.get("/api/search-runs").json()["total"] == 0


def test_archives_reuse_sources_validate_integrity_and_enforce_membership(client):
    source = indexed(client, "One", ["target phrase around"])
    a, b = create(client), create(client)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ArchivedText)) == 1
    outside = create(client, query="missing")
    assert (
        client.get(f"/api/search-runs/{outside['run_id']}/sources/{source['job_id']}").status_code
        == 404
    )
    with client.app.state.session_factory.begin() as session:
        session.execute(
            update(ArchivedText)
            .where(ArchivedText.processing_job_id == source["job_id"])
            .values(sha256="a" * 64)
        )
    assert (
        client.get(f"/api/search-runs/{a['run_id']}/sources/{source['job_id']}").status_code == 503
    )
    with client.app.state.session_factory.begin() as session:
        session.execute(
            update(SearchRun)
            .where(SearchRun.id == UUID(b["run_id"]))
            .values(snapshot_sha256="b" * 64)
        )
    assert client.get(f"/api/search-runs/{b['run_id']}").status_code == 503


def test_every_document_occurrence_and_unsearchable_page_is_preserved(client, monkeypatch):
    for index in range(28):
        indexed(client, f"Match {index}", ["target phrase around " * 6])
    for index in range(12):
        client.post(
            "/api/documents/upload",
            files={"file": ("pending.txt", b"pending")},
            data={"title": f"Pending {index}"},
        )
    run = create(client, limit=2, occurrence_limit=1, unsearchable_limit=2)
    assert len(run["results"]) == 2 and run["total"] == 28
    assert run["summary"]["occurrences_total"] == 168 and run["unsearchable_total"] == 12
    monkeypatch.setattr(
        search_runs, "textual_snapshot", lambda *args, **kwargs: pytest.fail("Recomputed")
    )
    last = client.get(
        f"/api/search-runs/{run['run_id']}",
        params={"offset": 26, "limit": 2, "unsearchable_offset": 10, "unsearchable_limit": 2},
    ).json()
    assert len(last["results"]) == len(last["unsearchable"]) == 2
    group = last["results"][0]
    occurrence = client.get(
        f"/api/search-runs/{run['run_id']}",
        params={"document_id": group["document"]["document_id"], "occurrence_offset": 5},
    ).json()
    assert len(occurrence["results"][0]["occurrences"]) == 1
    assert occurrence["results"][0]["occurrence_total"] == 6


def test_frozen_semantic_scores_need_no_model_and_review_filters_use_frozen_universe(
    client, monkeypatch
):
    from traystack.api import search_runs as api

    indexed(client, "Approximate", ["target phraze around"])
    monkeypatch.setattr(
        api,
        "get_engine",
        lambda *args: SimpleNamespace(
            compare=lambda query, texts: [(91.2345, 0.912345)] * len(texts),
            provenance=lambda: dict(
                model="old-model",
                pipeline="old-pipeline",
                score_version="old-score",
                max_tokens=128,
            ),
        ),
    )
    run = create(client, minimum_semantic_score=80, review_filter="keep")
    assert run["total"] == 0 and run["review_counts"]["unreviewed"] == 1
    monkeypatch.setattr(api, "get_engine", lambda *args: pytest.fail("Model called on reopen"))
    all_states = client.get(
        f"/api/search-runs/{run['run_id']}", params={"review_filter": "all"}
    ).json()
    assert all_states["results"][0]["occurrences"][0]["semantic_score"] == 91.2345
    payload = command(all_states)
    payload["search_run_id"] = run["run_id"]
    assert client.post("/api/reviews", json=payload).status_code == 200
    reviewed = client.get(f"/api/search-runs/{run['run_id']}").json()
    assert reviewed["review_filter"] == "keep" and reviewed["total"] == 1
    assert reviewed["semantic"]["model"] == "old-model"


def test_scope_and_semantic_failures_do_not_publish_partial_snapshots(client, monkeypatch):
    from traystack.api import search_runs as api

    indexed(client, "Matching", ["target phrase"])
    indexed(client, "Unmatched", ["Unrelated content"])
    client.app.state.settings.search_snapshot_max_documents = 1
    error = client.post("/api/search-runs", json={"search": {"query": "target phrase"}})
    assert error.status_code == 422
    assert error.json()["detail"]["resource"] == "snapshot_documents"
    client.app.state.settings.search_snapshot_max_documents = 10_000

    def unavailable(*args):
        raise SemanticUnavailable("Model unavailable")

    monkeypatch.setattr(api, "get_engine", unavailable)
    error = client.post(
        "/api/search-runs",
        json={"search": {"query": "target phrase", "minimum_semantic_score": 50}},
    )
    assert error.status_code == 503
    assert client.get("/api/search-runs").json()["total"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ArchivedText)) == 0


def test_replacement_between_capture_and_persistence_keeps_the_captured_source(client, monkeypatch):
    old = indexed(client, "Original", ["target phrase original"])
    original_snapshot = search_runs.textual_snapshot

    def capture_then_replace(*args, **kwargs):
        result = original_snapshot(*args, **kwargs)
        indexed(
            client,
            "Replacement",
            ["Entirely different revision"],
            document_id=old["document_id"],
            revision_number=2,
        )
        return result

    monkeypatch.setattr(search_runs, "textual_snapshot", capture_then_replace)
    saved = create(client)
    assert saved["results"][0]["document"]["revision_number"] == 1
    source = client.get(f"/api/search-runs/{saved['run_id']}/sources/{old['job_id']}")
    assert source.status_code == 200
    assert source.json()["plain_text"] == "target phrase original"
    payload = {**command(saved), "search_run_id": saved["run_id"]}
    assert client.post("/api/reviews", json=payload).status_code == 200
    assert client.post("/api/reviews", json=command(saved)).status_code == 409


def test_changed_archive_rejects_new_capture_atomically_and_view_rejects_outside_scope(client):
    old = indexed(client, "One", ["target phrase"])
    saved = create(client, document_id=str(old["document_id"]))
    other = indexed(client, "Outside", ["target phrase"])
    assert (
        client.get(
            f"/api/search-runs/{saved['run_id']}",
            params={"document_id": str(other["document_id"])},
        ).status_code
        == 422
    )
    payload = command(create(client, document_id=str(other["document_id"])))
    payload["search_run_id"] = saved["run_id"]
    assert client.post("/api/reviews", json=payload).status_code == 409
    with client.app.state.session_factory.begin() as session:
        session.execute(
            update(ArchivedText)
            .where(ArchivedText.processing_job_id == old["job_id"])
            .values(sha256="a" * 64)
        )
    # This newly encountered source is inserted before the older conflicting
    # archive; the transaction must roll that insertion back as well.
    indexed(client, "Newest source", ["target phrase"])
    error = client.post("/api/search-runs", json={"search": {"query": "target phrase"}})
    assert error.status_code == 409
    assert client.get("/api/search-runs").json()["total"] == 2
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ArchivedText)) == 2

from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_reviews import command
from test_search import indexed

from traystack.api import search_runs as api
from traystack.models import PassageReview

pytestmark = pytest.mark.integration


def engine(monkeypatch):
    monkeypatch.setattr(
        api,
        "get_engine",
        lambda *a: SimpleNamespace(
            provenance=lambda: dict(
                model="test", pipeline="test", score_version="v1", max_tokens=128
            ),
            compare=lambda query, texts: [
                (100.0, 1.0) if query == text else (90.0, 0.9) for text in texts
            ],
        ),
    )


def run(client, monkeypatch, **extra):
    engine(monkeypatch)
    response = client.post(
        "/api/search-runs",
        json={
            "search": {
                "query": "target phrase",
                "minimum_score": 85,
                "minimum_semantic_score": 0,
                "ready_only": True,
                "auto_confirm_textual": 100,
                "auto_confirm_semantic": 100,
                **extra,
            }
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def workspace(client, saved):
    response = client.get(f"/api/search-runs/{saved['run_id']}/workspace")
    assert response.status_code == 200, response.text
    return response.json()


def test_automatic_confirmation_and_manual_override_are_read_only_and_persistent(
    client, monkeypatch
):
    indexed(client, "Exact", ["target phrase"])
    saved = run(client, monkeypatch)
    item = saved["results"][0]["occurrences"][0]
    assert item["auto_confirmed"] and item["review"]["decision"] == "keep"
    assert item["review"]["version"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PassageReview)) == 0
    payload = {**command(saved), "search_run_id": saved["run_id"], "decision": "unreviewed"}
    assert client.post("/api/reviews", json=payload).status_code == 200
    current = workspace(client, saved)
    item = current["results"][0]["occurrences"][0]
    assert not item["auto_confirmed"] and item["review"]["decision"] == "unreviewed"
    assert item["review_at_capture"]["decision"] == "keep"
    assert current["document_outcomes"][0]["state"] == "unreviewed"
    # Reopening never runs retrieval or the model and cannot override a reset.
    monkeypatch.setattr(api, "get_engine", lambda *a: pytest.fail("Model called"))
    assert workspace(client, saved)["results"][0]["occurrences"][0] == item
    assert client.post("/api/reviews", json=payload).status_code == 409


def test_auto_thresholds_and_document_groups_cover_full_scope(client, monkeypatch):
    indexed(client, "Exact", ["target phrase"])
    indexed(client, "Approximate", ["target phraze"])
    indexed(client, "No candidate", ["Completely unrelated schedule"])
    saved = run(client, monkeypatch, limit=1, occurrence_limit=1)
    current = workspace(client, saved)
    assert {row["document"]["title"]: row["state"] for row in current["document_outcomes"]} == {
        "Exact": "confirmed",
        "Approximate": "unreviewed",
        "No candidate": "no_active_match",
    }
    approximate = next(
        group for group in current["results"] if group["document"]["title"] == "Approximate"
    )
    selected = {**current, "results": [approximate]}
    payload = {**command(selected), "search_run_id": saved["run_id"], "decision": "dismiss"}
    assert client.post("/api/reviews", json=payload).status_code == 200
    outcomes = workspace(client, saved)["document_outcomes"]
    assert (
        next(row for row in outcomes if row["document"]["title"] == "Approximate")["state"]
        == "no_active_match"
    )
    # Less strict explicit policy can confirm a nonidentical candidate.
    indexed(client, "New approximate", ["target phruse"])
    broader = run(client, monkeypatch, auto_confirm_textual=80, auto_confirm_semantic=80)
    new_group = next(
        group
        for group in workspace(client, broader)["results"]
        if group["document"]["title"] == "New approximate"
    )
    assert new_group["occurrences"][0]["auto_confirmed"]
    # Explicit dismissal wins even under a more permissive policy.
    candidate = next(
        group
        for group in workspace(client, broader)["results"]
        if group["document"]["title"] == "Approximate"
    )["occurrences"][0]
    assert candidate["review"]["decision"] == "dismiss" and not candidate["auto_confirmed"]


def test_categories_filter_before_scope_capture_and_do_not_rewrite_old_runs(client, monkeypatch):
    source = indexed(client, "Supply", ["target phrase"])
    other = indexed(client, "Employment", ["target phrase"])
    indexed(client, "Uncategorized", ["target phrase"])
    for identity, category in [
        (source["document_id"], "Supply"),
        (other["document_id"], "Employment"),
    ]:
        response = client.patch(f"/api/documents/{identity}/category", json={"category": category})
        assert response.status_code == 200, response.text
    assert client.get("/api/categories").json()["items"] == ["Employment", "Supply"]
    saved = run(client, monkeypatch, category="Supply")
    assert saved["scope_total"] == 1
    assert saved["results"][0]["document"]["category"] == "Supply"
    assert (
        client.patch(
            f"/api/documents/{source['document_id']}/category", json={"category": "Renamed"}
        ).status_code
        == 200
    )
    assert workspace(client, saved)["document_outcomes"][0]["document"]["category"] == "Supply"
    assert run(client, monkeypatch, category="Supply")["scope_total"] == 0
    assert run(client, monkeypatch, uncategorized=True)["scope_total"] == 1
    assert (
        client.post(
            "/api/search-runs",
            json={
                "search": {"query": "target phrase", "category": "Supply", "uncategorized": True}
            },
        ).status_code
        == 422
    )


def test_upload_category_roundtrip_validation_and_metadata_preservation(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("a.txt", b"target phrase")},
        data={"title": "Categorized", "category": " Supply ", "metadata": '{"note":"preserve"}'},
    )
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["metadata"] == {"note": "preserve", "category": "Supply"}
    changed = client.patch(f"/api/documents/{doc['id']}/category", json={"category": None})
    assert changed.json()["metadata"] == {"note": "preserve"}
    assert (
        client.patch(
            f"/api/documents/{doc['id']}/category", json={"category": "x" * 101}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/documents/{UUID(int=0)}/category", json={"category": "Other"}
        ).status_code
        == 404
    )


def test_legacy_deferred_state_is_unreviewed_in_workspace_and_ui_export(client, monkeypatch):
    indexed(client, "Old decision", ["target phrase"])
    saved = run(client, monkeypatch, auto_confirm_textual=None, auto_confirm_semantic=None)
    assert (
        client.post(
            "/api/reviews",
            json={**command(saved), "search_run_id": saved["run_id"], "decision": "later"},
        ).status_code
        == 200
    )
    assert (
        workspace(client, saved)["results"][0]["occurrences"][0]["review"]["decision"]
        == "unreviewed"
    )
    exported = client.get(
        f"/api/search-runs/{saved['run_id']}/export",
        params={"format": "json", "review_filter": "unreviewed", "three_state": True},
    )
    assert exported.status_code == 200
    assert exported.json()["result"]["summary"]["occurrences_total"] == 1


def test_auto_confirmation_uses_unrounded_textual_score(client, monkeypatch):
    indexed(client, "Rounding boundary", ["target phraze"])
    saved = run(client, monkeypatch, auto_confirm_textual=92.307695, auto_confirm_semantic=80)
    item = workspace(client, saved)["results"][0]["occurrences"][0]
    assert item["score"] == 92.3077
    assert item["raw_textual_score"] < 92.307695
    assert not item["auto_confirmed"]


def test_auto_confirmation_uses_unrounded_semantic_score(client, monkeypatch):
    indexed(client, "Semantic rounding", ["target phraze"])
    monkeypatch.setattr(
        api,
        "get_engine",
        lambda *a: SimpleNamespace(
            provenance=lambda: dict(
                model="test", pipeline="test", score_version="v1", max_tokens=128
            ),
            compare=lambda query, texts: [(90.000049, 0.90000049)] * len(texts),
        ),
    )
    response = client.post(
        "/api/search-runs",
        json={
            "search": {
                "query": "target phrase",
                "minimum_semantic_score": 0,
                "auto_confirm_textual": 0,
                "auto_confirm_semantic": 90.000025,
            }
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()["results"][0]["occurrences"][0]
    assert item["semantic_score"] == 90.0
    assert item["raw_semantic_score"] > 90.000025 and item["auto_confirmed"]


def test_ephemeral_category_echo_and_explicit_auto_policy_rejection(client):
    indexed(client, "Uncategorized", ["target phrase"])
    response = client.post(
        "/api/search/textual", json={"query": "target phrase", "uncategorized": True}
    )
    assert response.status_code == 200
    assert response.json()["uncategorized"] is True
    response = client.post(
        "/api/search/textual",
        json={
            "query": "target phrase",
            "minimum_semantic_score": 0,
            "auto_confirm_textual": 100,
            "auto_confirm_semantic": 100,
        },
    )
    assert response.status_code == 422

"""Customer search excludes documents before readiness, including failed reprocessing."""

import pytest
from test_search import indexed

pytestmark = pytest.mark.integration


def test_ready_scope_is_shared_by_literal_and_textual_search(client):
    indexed(client, "Ready positive", ["target phrase"])
    indexed(client, "Ready negative", ["Different contract text"])
    indexed(client, "Whitespace only", [" \t\n"])
    indexed(client, "Incomplete", ["target phrase", ""], failed_pages=(2,))
    indexed(client, "Flagged", ["target phrase"], manual=True)
    indexed(client, "Quality issue", ["target phrase"], quality="needs_review")
    pending = client.post(
        "/api/documents/upload",
        files={"file": ("pending.txt", b"target phrase")},
        data={"title": "Pending"},
    )
    assert pending.status_code == 201
    request = {"query": "target phrase", "ready_only": True}
    found = client.post("/api/search", json=request).json()
    assert found["summary"]["documents_total"] == 2
    assert found["unverifiable_total"] == 0
    assert [row["title"] for row in found["results"]] == ["Ready positive"]
    absent = client.post("/api/search", json={**request, "relation": "lacks"}).json()
    assert [row["title"] for row in absent["results"]] == ["Ready negative"]
    similar = client.post("/api/search/textual", json=request).json()
    assert similar["summary"]["documents_total"] == 2
    assert similar["unsearchable_total"] == 0
    assert [row["document"]["title"] for row in similar["results"]] == ["Ready positive"]
    saved = client.post("/api/search-runs", json={"search": request}).json()
    assert saved["scope_total"] == 2
    assert saved["unsearchable_total"] == 0


def test_new_revision_or_pending_reprocessing_is_not_ready(client):
    source = indexed(client, "Original", ["target phrase"])
    request = {"query": "target phrase", "ready_only": True}
    assert client.post("/api/search", json=request).json()["total"] == 1
    assert (
        client.post(f"/api/revisions/{source['revision_id']}/process", json={}).status_code == 202
    )
    assert client.post("/api/search", json=request).json()["summary"]["documents_total"] == 0
    assert (
        client.post("/api/search/textual", json=request).json()["summary"]["documents_total"] == 0
    )
    # The diagnostic API still exposes the retained source and pending-run warning.
    assert client.post("/api/search", json={"query": "target phrase"}).json()["total"] == 1

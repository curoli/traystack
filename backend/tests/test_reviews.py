from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_search import indexed

from traystack.api import search as search_api
from traystack.models import PassageReview
from traystack.services.processing import run_once

pytestmark = pytest.mark.integration


def search(client, query="target phrase", **extra):
    response = client.post(
        "/api/search/textual", json={"query": query, "minimum_score": 100, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


def command(result, group=0, occurrence=0, decision="keep"):
    doc = result["results"][group]["document"]
    item = result["results"][group]["occurrences"][occurrence]
    return dict(
        occurrence_id=item["occurrence_id"],
        document_id=doc["document_id"],
        revision_id=doc["revision_id"],
        processing_job_id=doc["processing_job_id"],
        source_artifact_id=doc["artifact_id"],
        normalization_version=doc["normalization_version"],
        query=result["query"],
        mode=result["mode"],
        scorer_version=result["scorer_version"],
        candidate_policy=result["candidate_policy"],
        start_offset=item["start_offset"],
        end_offset=item["end_offset"],
        matched_sha256=item["matched_sha256"],
        expected_version=item["review"]["version"],
        decision=decision,
    )


def stored(client):
    with client.app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(PassageReview))


def test_decisions_persist_change_reset_and_never_get_created_by_reading(client):
    indexed(client, "Reviewed", ["😀 target phrase trailing text"])
    result = search(client)
    assert result["review_counts"] == dict(unreviewed=1, keep=0, dismiss=0, later=0)
    assert stored(client) == 0
    payload = command(result)
    assert payload["start_offset"] == 2  # Unicode code points, not UTF-16 offsets.
    for version, decision in enumerate(["keep", "dismiss", "later", "unreviewed"], 1):
        response = client.post("/api/reviews", json={**payload, "decision": decision})
        assert response.status_code == 200, response.text
        assert response.json()["decision"] == decision
        assert response.json()["version"] == version
        assert response.json()["updated_at"]
        again = search(client)
        assert again["results"][0]["occurrences"][0]["review"] == response.json()
        assert again["review_counts"][decision] == 1
        payload["expected_version"] = version
    assert stored(client) == 1
    stale = client.post("/api/reviews", json={**payload, "expected_version": 0})
    assert stale.status_code == 409
    assert search(client)["results"][0]["occurrences"][0]["review"]["version"] == 4


def test_identity_tracks_expression_mode_source_and_occurrence_but_not_thresholds(
    client, monkeypatch
):
    indexed(client, "Repeated", ["target phrase around target phrase around"])
    result = search(client)
    first = command(result)
    assert client.post("/api/reviews", json=first).status_code == 200
    assert search(client, query="TARGET PHRASE")["review_counts"]["keep"] == 1
    changed_threshold = search(client, minimum_score=85)
    assert changed_threshold["review_counts"]["keep"] == 1
    assert changed_threshold["review_counts"]["unreviewed"] == 1
    monkeypatch.setattr(
        search_api,
        "get_engine",
        lambda *args: SimpleNamespace(
            compare=lambda query, texts: [(100, 1)] * len(texts),
            provenance=lambda: dict(
                model="test", pipeline="test", score_version="test", max_tokens=128
            ),
        ),
    )
    assert search(client, minimum_semantic_score=0)["review_counts"]["keep"] == 1
    assert search(client, mode="exact")["review_counts"]["keep"] == 0
    other = search(client, query="target phraze", minimum_score=85)
    assert other["results"][0]["occurrences"][0]["start_offset"] == first["start_offset"]
    assert other["results"][0]["occurrences"][0]["end_offset"] == first["end_offset"]
    assert other["review_counts"]["keep"] == 0
    indexed(client, "Same bytes, other document", ["target phrase around target phrase around"])
    both = search(client)
    assert both["review_counts"]["keep"] == 1
    assert both["review_counts"]["unreviewed"] == 3


def test_review_filter_counts_all_matching_passages_before_both_pages(client):
    indexed(client, "Many", ["target phrase around " * 7])
    indexed(client, "Other", ["target phrase around " * 3])
    result = search(client, occurrence_limit=25)
    for index, decision in enumerate(["keep", "keep", "dismiss", "later"]):
        # The latest document has three occurrences; the fourth belongs to the other doc.
        payload = command(
            result,
            group=0 if index < 3 else 1,
            occurrence=index if index < 3 else 0,
            decision=decision,
        )
        assert client.post("/api/reviews", json=payload).status_code == 200
    counts = dict(unreviewed=6, keep=2, dismiss=1, later=1)
    for state, total in counts.items():
        filtered = search(client, review_filter=state, limit=1, occurrence_limit=1)
        assert filtered["review_counts"] == counts
        assert filtered["summary"]["occurrences_total"] == total
        assert len(filtered["results"]) == 1
        assert filtered["results"][0]["occurrences"][0]["review"]["decision"] == state
        doc_id = filtered["results"][0]["document"]["document_id"]
        scoped = search(client, review_filter=state, document_id=doc_id, occurrence_limit=1)
        assert (
            scoped["results"][0]["occurrence_total"] == filtered["results"][0]["occurrence_total"]
        )
    missing = search(client, query="missing", review_filter="keep")
    assert missing["review_counts"] == dict(unreviewed=0, keep=0, dismiss=0, later=0)
    assert missing["total"] == 0


@pytest.mark.parametrize("replace", ["processing", "revision"])
def test_replaced_source_keeps_old_review_but_rejects_stale_saves(client, replace):
    source = indexed(client, "Original", ["target phrase around"])
    old = search(client)
    payload = command(old)
    assert client.post("/api/reviews", json=payload).status_code == 200
    payload["expected_version"] = 1
    if replace == "processing":
        queued = client.post(f"/api/revisions/{source['revision_id']}/process", json={})
        assert queued.status_code == 202
        # A pending run does not replace selected text yet.
        assert client.post("/api/reviews", json={**payload, "decision": "later"}).status_code == 200
        assert run_once(client.app.state.session_factory, client.app.state.storage)
    else:
        indexed(
            client,
            "New revision",
            ["target phrase around"],
            document_id=source["document_id"],
            revision_number=2,
        )
    assert client.post("/api/reviews", json=payload).status_code == 409
    new = search(client)
    assert new["review_counts"] == dict(unreviewed=1, keep=0, dismiss=0, later=0)
    assert new["results"][0]["occurrences"][0]["occurrence_id"] != payload["occurrence_id"]
    assert stored(client) == 1


@pytest.mark.parametrize("version", [0, 1])
def test_concurrent_saves_cannot_silently_overwrite_a_review(client, version):
    indexed(client, "Concurrent", ["target phrase around"])
    payload = command(search(client))
    if version:
        assert client.post("/api/reviews", json=payload).status_code == 200
    payload["expected_version"] = version
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda decision: client.post(
                    "/api/reviews", json={**payload, "decision": decision}
                ),
                ["dismiss", "later"],
            )
        )
    assert sorted(item.status_code for item in responses) == [200, 409]
    successful = next(item.json() for item in responses if item.status_code == 200)
    assert search(client)["results"][0]["occurrences"][0]["review"] == successful
    assert successful["version"] == version + 1
    assert stored(client) == 1


def test_invalid_identity_source_and_offsets_never_write_a_review(client):
    indexed(client, "Validated", ["target phrase around"])
    payload = command(search(client))
    for change in [
        dict(occurrence_id="a" * 64),
        dict(matched_sha256="b" * 64),
        dict(end_offset=2000),
        dict(source_artifact_id=str(uuid4())),
        dict(document_id=str(uuid4())),
        dict(revision_id=str(uuid4())),
        dict(processing_job_id=str(uuid4())),
        dict(query="different"),
        dict(normalization_version="different"),
        dict(scorer_version="old"),
        dict(candidate_policy="old"),
        dict(mode="exact"),
    ]:
        assert client.post("/api/reviews", json={**payload, **change}).status_code == 409
    for change in [
        dict(decision="approved"),
        dict(start_offset=-1),
        dict(end_offset=0),
        dict(expected_version=-1),
        dict(extra=True),
        dict(query=" "),
    ]:
        assert client.post("/api/reviews", json={**payload, **change}).status_code == 422
    assert stored(client) == 0
    assert client.post("/api/reviews", json=payload).status_code == 200


def test_casefold_expansion_is_stored_without_truncating_query(client):
    query = "ß" * 500
    indexed(client, "Expanded Unicode", [query])
    result = search(client, query=query)
    assert len(result["effective_query"]) == 1000
    response = client.post("/api/reviews", json=command(result))
    assert response.status_code == 200, response.text
    assert search(client, query=query)["review_counts"]["keep"] == 1


def test_semantic_filter_precedes_review_counts_and_review_filter(client, monkeypatch):
    indexed(client, "Semantic", ["target phrase around target phraze around"])
    all_textual = search(client, minimum_score=85)
    assert client.post("/api/reviews", json=command(all_textual, occurrence=1)).status_code == 200
    monkeypatch.setattr(
        search_api,
        "get_engine",
        lambda *args: SimpleNamespace(
            compare=lambda query, texts: [
                (100, 1) if query == text else (40, 0.4) for text in texts
            ],
            provenance=lambda: dict(
                model="test", pipeline="test", score_version="test", max_tokens=128
            ),
        ),
    )
    result = search(client, minimum_score=85, minimum_semantic_score=80, review_filter="keep")
    assert result["textual_candidates_total"] == 2
    assert result["review_counts"] == dict(unreviewed=1, keep=0, dismiss=0, later=0)
    assert result["total"] == 0

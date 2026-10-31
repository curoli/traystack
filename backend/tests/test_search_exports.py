"""Complete stored-run exports, historical provenance and consistent review state."""

import csv
import io
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from test_reviews import command
from test_search import indexed
from test_search_runs import create

from traystack.models import SearchRun
from traystack.services import search_exports, search_runs
from traystack.services.processing import run_once

pytestmark = pytest.mark.integration


def export(client, run, format="json", state="all"):
    return client.get(
        f"/api/search-runs/{run['run_id']}/export",
        params={"format": format, "review_filter": state},
    )


def csv_rows(response):
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_exports_include_every_page_occurrence_and_unknown_without_retrieval(client, monkeypatch):
    for index in range(28):
        indexed(client, f"Match {index}", ["target phrase around " * 6])
    for index in range(12):
        client.post(
            "/api/documents/upload",
            files={"file": ("pending.txt", b"pending")},
            data={"title": f"Pending {index}"},
        )
    run = create(client, limit=1, offset=25, occurrence_limit=1, unsearchable_limit=1)
    assert len(run["results"]) == 1
    monkeypatch.setattr(
        search_runs, "textual_snapshot", lambda *a, **k: pytest.fail("Export reran retrieval")
    )
    response = export(client, run)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].endswith('-all.json"')
    payload = response.json()
    assert payload["schema_version"] == 1
    assert len(payload["captured_scope"]) == 40
    body = payload["result"]
    assert len(body["results"]) == 28 and len(body["unsearchable"]) == 12
    assert sum(len(group["occurrences"]) for group in body["results"]) == 168
    assert body["summary"]["occurrences_total"] == 168
    assert "limit" not in body and "occurrence_limit" not in body["results"][0]
    rows = csv_rows(export(client, run, "csv"))
    assert len(rows) == 1 + 168 + 12
    assert sum(row["row_type"] == "passage" for row in rows) == 168
    assert rows[0]["row_type"] == "summary"
    assert rows[0]["exported_passages"] == "168"
    assert rows[0]["unsearchable_documents"] == "12"
    assert all(row["searched_at"] == run["searched_at"] for row in rows)
    assert all(row["exported_at"] for row in rows)


@pytest.mark.parametrize("state", ["all", "keep", "dismiss", "later", "unreviewed"])
def test_filters_use_current_decisions_and_preserve_capture_state(client, state):
    indexed(client, "Decisions", ["target phrase around " * 5])
    run = create(client, review_filter="keep")
    all_states = client.get(
        f"/api/search-runs/{run['run_id']}", params={"review_filter": "all"}
    ).json()
    base = command(all_states)
    for item, decision in zip(
        all_states["results"][0]["occurrences"], ["keep", "dismiss", "later"], strict=False
    ):
        response = client.post(
            "/api/reviews",
            json={
                **base,
                "search_run_id": run["run_id"],
                "decision": decision,
                **{
                    key: item[key]
                    for key in (
                        "occurrence_id",
                        "start_offset",
                        "end_offset",
                        "matched_sha256",
                    )
                },
            },
        )
        assert response.status_code == 200, response.text
    payload = export(client, run, state=state).json()
    assert payload["request"]["review_filter"] == "keep"
    assert payload["result"]["review_filter"] == state
    occurrences = [item for group in payload["result"]["results"] for item in group["occurrences"]]
    expected = 5 if state == "all" else (2 if state == "unreviewed" else 1)
    assert len(occurrences) == expected
    assert all(item["review_at_capture"]["decision"] == "unreviewed" for item in occurrences)
    if state != "all":
        assert all(item["review"]["decision"] == state for item in occurrences)
    rows = csv_rows(export(client, run, "csv", state))
    passages = [row for row in rows if row["row_type"] == "passage"]
    assert len(passages) == expected
    assert {row["review_decision"] for row in passages} == {
        item["review"]["decision"] for item in occurrences
    }


def test_empty_filtered_export_retains_metadata_scope_and_unknowns(client):
    indexed(client, "Unreviewed", ["target phrase"])
    pending = client.post(
        "/api/documents/upload",
        files={"file": ("pending.txt", b"unprocessed")},
        data={"title": "Pending source"},
    )
    assert pending.status_code == 201, pending.text
    run = create(client)
    payload = export(client, run, state="keep").json()
    assert payload["result"]["results"] == []
    assert len(payload["captured_scope"]) == 2
    rows = csv_rows(export(client, run, "csv", "keep"))
    assert [row["row_type"] for row in rows] == ["summary", "unsearchable"]
    assert rows[0]["exported_passages"] == "0"
    assert rows[0]["run_id"] == run["run_id"]
    assert rows[0]["exported_at"] and rows[0]["searched_at"]
    no_matches = create(client, query="nonexistent expression")
    assert export(client, no_matches).json()["result"]["results"] == []
    assert len(csv_rows(export(client, no_matches, "csv"))) == 2


def test_historical_export_keeps_scores_text_and_provenance_after_reprocessing(client):
    old = indexed(client, "Original title", ["target phraze context"])
    run = create(client)
    before = export(client, run).json()
    assert client.post(f"/api/revisions/{old['revision_id']}/process", json={}).status_code == 202
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    indexed(client, "New match", ["target phrase"])
    response = client.post(f"/api/search-runs/{run['run_id']}/name", json={"name": "Renamed"})
    assert response.status_code == 200
    after = export(client, run).json()
    assert after["result"]["results"] == before["result"]["results"]
    assert after["captured_scope"] == before["captured_scope"]
    assert after["run"]["snapshot_sha256"] == before["run"]["snapshot_sha256"]
    assert after["run"]["name"] == "Renamed"
    rows = csv_rows(export(client, run, "csv"))
    assert rows[1]["processing_job_id"] == str(old["job_id"])
    assert rows[1]["matched_text"] == "target phraze"
    assert float(rows[1]["textual_score"]) < 100


def test_export_reviews_share_one_snapshot_even_when_another_view_saves(client, monkeypatch):
    indexed(client, "One", ["target phrase"])
    run = create(client)
    original_read = search_exports.read_run
    changed = False

    def save_before_read(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            response = client.post(
                "/api/reviews",
                json={
                    **command(run),
                    "search_run_id": run["run_id"],
                },
            )
            assert response.status_code == 200
        return original_read(*args, **kwargs)

    monkeypatch.setattr(search_exports, "read_run", save_before_read)
    first = export(client, run).json()
    assert first["result"]["review_counts"]["unreviewed"] == 1
    assert first["result"]["results"][0]["occurrences"][0]["review"]["decision"] == "unreviewed"
    assert export(client, run).json()["result"]["review_counts"]["keep"] == 1


@pytest.mark.parametrize(
    "value", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1)", " \t\r\n=1+1", "\u00a0=1+1", "\v=1+1"]
)
def test_csv_formula_protection_preserves_exact_text_in_json(client, value):
    indexed(client, value, [f'{value} context, "quoted"\nStraße 😀'])
    run = create(client, query=value, mode="exact", minimum_score=100)
    payload = export(client, run).json()
    assert payload["result"]["query"] == value
    assert payload["result"]["results"][0]["occurrences"][0]["matched_text"] == value
    rows = csv_rows(export(client, run, "csv"))
    assert rows[0]["query"] == "'" + value
    assert rows[1]["document_title"] == "'" + value
    assert rows[1]["matched_text"] == "'" + value
    assert rows[1]["context"] == "'" + f'{value} context, "quoted"\nStraße 😀'


def test_export_rejects_invalid_filters_unknown_runs_and_corrupt_snapshots(client):
    indexed(client, "One", ["target phrase"])
    run = create(client)
    assert export(client, run, "pdf").status_code == 422
    assert export(client, run, state="invalid").status_code == 422
    assert export(client, {"run_id": str(uuid4())}).status_code == 404
    with client.app.state.session_factory.begin() as session:
        session.execute(
            update(SearchRun)
            .where(SearchRun.id == UUID(run["run_id"]))
            .values(
                snapshot_sha256="a" * 64,
            )
        )
    for format in ("csv", "json"):
        response = export(client, run, format)
        assert response.status_code == 503
        assert "content-disposition" not in response.headers


def test_semantic_values_and_versions_are_exported_without_loading_the_model(client, monkeypatch):
    from types import SimpleNamespace

    from traystack.api import search_runs as api

    indexed(client, "Semantic", ["target phraze"])
    provenance = dict(
        model="pinned-model", pipeline="pinned-pipeline", score_version="v1", max_tokens=128
    )
    monkeypatch.setattr(
        api,
        "get_engine",
        lambda *a: SimpleNamespace(
            provenance=lambda: provenance,
            compare=lambda query, texts: [(91.2345, 0.912345)] * len(texts),
        ),
    )
    run = create(client, minimum_semantic_score=80)
    monkeypatch.setattr(api, "get_engine", lambda *a: pytest.fail("Export loaded model"))
    payload = export(client, run).json()
    assert payload["result"]["semantic"] == provenance
    item = payload["result"]["results"][0]["occurrences"][0]
    assert item["semantic_score"] == 91.2345 and item["semantic_cosine"] == 0.912345
    assert item["differences"] == run["results"][0]["occurrences"][0]["differences"]
    row = csv_rows(export(client, run, "csv"))[1]
    assert row["semantic_model"] == "pinned-model"
    assert row["semantic_pipeline"] == "pinned-pipeline"
    assert row["semantic_score"] == "91.2345"
    assert row["semantic_cosine"] == "0.912345"

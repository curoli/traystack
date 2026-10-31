"""The bounded saved-run workspace spans every result page without new retrieval."""

import pytest
from test_reviews import command
from test_search import indexed
from test_search_runs import create

from traystack.services import search_runs

pytestmark = pytest.mark.integration


def test_workspace_loads_all_matches_and_current_reviews_without_changing_snapshot(
    client, monkeypatch
):
    for index in range(28):
        indexed(client, f"Document {index}", ["target phrase around " * 6])
    run = create(client, limit=1, occurrence_limit=1, offset=25)
    monkeypatch.setattr(
        search_runs, "textual_snapshot", lambda *a, **k: pytest.fail("Retrieval called")
    )
    response = client.get(f"/api/search-runs/{run['run_id']}/workspace")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    all_results = response.json()
    assert len(all_results["results"]) == 28
    assert all_results["limit"] == 28 and all_results["offset"] == 0
    assert all(
        group["occurrence_limit"] == 6 and group["occurrence_offset"] == 0
        for group in all_results["results"]
    )
    assert sum(len(group["occurrences"]) for group in all_results["results"]) == 168
    payload = {**command(all_results), "search_run_id": run["run_id"]}
    assert client.post("/api/reviews", json=payload).status_code == 200
    kept = client.get(
        f"/api/search-runs/{run['run_id']}/workspace", params={"review_filter": "keep"}
    ).json()
    assert kept["summary"]["occurrences_total"] == 1
    assert kept["review_counts"]["unreviewed"] == 167
    assert kept["results"][0]["occurrences"][0]["review_at_capture"]["decision"] == "unreviewed"
    assert (
        client.get(
            f"/api/search-runs/{run['run_id']}/workspace", params={"review_filter": "invalid"}
        ).status_code
        == 422
    )
    # Ordinary result pagination remains unchanged.
    assert len(client.get(f"/api/search-runs/{run['run_id']}").json()["results"]) == 10

import os
import socket
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_search import indexed

from traystack.api import search as search_api
from traystack.services.semantic import (
    SemanticEngine,
    SemanticInputTooLong,
    SemanticUnavailable,
    semantic_score,
)


def test_semantic_scale_reserves_100_for_comparison_identity():
    assert semantic_score("a", "a", 0.999999) == 100
    assert semantic_score("a", "b", 1) == 99.99
    assert semantic_score("a", "b", -0.2) == 0
    assert semantic_score("a", "b", 0.75) == 75


@pytest.fixture
def fake_engine(monkeypatch):
    calls = []

    def compare(query, passages):
        calls.append((query, passages))
        return [(100, 1) if text == query else (60, 0.6) for text in passages]

    engine = SimpleNamespace(
        compare=compare,
        provenance=lambda: dict(
            model="test-model", pipeline="test-v1", score_version="test", max_tokens=128
        ),
    )
    monkeypatch.setattr(search_api, "get_engine", lambda *args: engine)
    return calls


@pytest.mark.integration
def test_semantic_filters_all_candidates_before_counts_and_pagination(client, fake_engine):
    indexed(client, "Mixed", ["Keep this clause. Keep that clause."])
    indexed(client, "Different", ["Keep that clause."])
    payload = {
        "query": "Keep this clause",
        "minimum_score": 60,
        "minimum_semantic_score": 80,
        "limit": 1,
        "occurrence_limit": 1,
    }
    result = client.post("/api/search/textual", json=payload)
    assert result.status_code == 200
    body = result.json()
    assert body["textual_candidates_total"] == 3
    assert body["summary"]["occurrences_total"] == 1
    assert body["summary"]["documents_with_matches"] == 1
    assert body["summary"]["documents_without_matches"] == 1
    assert body["results"][0]["occurrence_total"] == 1
    assert body["results"][0]["occurrences"][0]["semantic_score"] == 100
    assert len(fake_engine[-1][1]) == 3  # Not just the requested page.
    all_scores = client.post(
        "/api/search/textual", json={**payload, "minimum_semantic_score": 0}
    ).json()
    assert all_scores["summary"]["occurrences_total"] == 3
    assert all_scores["minimum_semantic_score"] == 0
    assert "permissive_semantic_threshold" in all_scores["warnings"]
    strict = client.post(
        "/api/search/textual", json={**payload, "minimum_semantic_score": 100}
    ).json()
    assert strict["summary"]["occurrences_total"] == 1
    assert "semantic_exact_only" in strict["warnings"]
    for score in [-1, 101, "NaN", "Infinity"]:
        assert (
            client.post(
                "/api/search/textual", json={**payload, "minimum_semantic_score": score}
            ).status_code
            == 422
        )


@pytest.mark.integration
def test_semantic_is_optional_and_failure_never_falls_back_to_success(client, monkeypatch):
    indexed(client, "One", ["A valid contract clause"])

    def unavailable(*args):
        raise SemanticUnavailable("Semantic model is unavailable.")

    monkeypatch.setattr(search_api, "get_engine", unavailable)
    payload = {"query": "valid contract", "minimum_score": 100}
    assert client.post("/api/search/textual", json=payload).status_code == 200
    failed = client.post("/api/search/textual", json={**payload, "minimum_semantic_score": 0})
    assert failed.status_code == 503
    assert set(failed.json()) == {"detail"}
    assert (
        client.post("/api/search", json={"query": "missing", "relation": "lacks"}).json()["total"]
        == 1
    )


@pytest.mark.integration
def test_semantic_candidate_budget_aborts_before_loading_model(client, monkeypatch):
    for index in range(3):
        indexed(client, f"Repeated {index}", ["target " * 200])
    monkeypatch.setattr(search_api, "get_engine", lambda *args: pytest.fail("Model must not load"))
    response = client.post(
        "/api/search/textual",
        json={"query": "target", "minimum_score": 100, "minimum_semantic_score": 0},
    )
    assert response.status_code == 422
    assert set(response.json()) == {"detail"}
    detail = response.json()["detail"]
    assert detail["reason"] == "semantic_passage_limit"
    assert detail["observed_at_least"] == 600
    assert detail["documents_inspected"] == 3
    assert detail["results_complete"] is False


@pytest.fixture
def real_engine(tmp_path):
    root = os.environ.get("SEMANTIC_MODEL_PATH")
    if not root:
        pytest.skip("Set SEMANTIC_MODEL_PATH to the prepared pinned model for offline model tests")
    return SemanticEngine(Path(root), tmp_path / "cache")


def test_real_model_offline_cache_and_no_silent_truncation(real_engine, monkeypatch):
    # No test double for inference: exercise the real quantized model without sockets.
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("Network accessed"))
    query = "The receiving party shall not disclose confidential information."
    passages = [
        query,
        "The receiving party shall disclose confidential information.",
        "The receiving party shall not share confidential information.",
        "The price is EUR 500.",
        "The price is EUR 5000.",
    ]
    scores = real_engine.compare(query, passages)
    assert scores[0][0] == 100
    assert all(0 <= score < 100 and -1 <= cosine <= 1 for score, cosine in scores[1:])
    assert scores[1][0] > 50  # A negation change can retain high model similarity.
    assert len(list(real_engine.cache_path.glob("*.json"))) == 5
    original_session = real_engine.session
    real_engine.session = SimpleNamespace(run=lambda *args: pytest.fail("Cache not used"))
    assert np.allclose(real_engine.compare(query, passages), scores)
    real_engine.session = original_session
    # Corrupt derived cache data is regenerated, never used as a semantic score.
    real_engine._cache_file(query).write_text("[null]")
    assert np.allclose(real_engine.compare(query, passages), scores)
    with pytest.raises(SemanticInputTooLong, match="No text was truncated"):
        real_engine.compare("word " * 200, [query])
    assert real_engine.tokenizer.truncation is None

    def inference_failure(*args):
        raise RuntimeError("Simulated local runtime failure")

    real_engine.session = SimpleNamespace(run=inference_failure)
    with pytest.raises(SemanticUnavailable, match="No results were returned"):
        real_engine.compare("Uncached expression", [query])
    real_engine.session = original_session
    assert real_engine.gate.acquire(blocking=False)
    try:
        with pytest.raises(SemanticUnavailable, match="busy"):
            real_engine.compare(query, passages)
    finally:
        real_engine.gate.release()


@pytest.mark.integration
def test_real_api_scores_and_identity_modes(client, real_engine, monkeypatch):
    monkeypatch.setattr(search_api, "get_engine", lambda *args: real_engine)
    indexed(client, "Case", ["THE receiving party shall not disclose information."])
    payload = {
        "query": "The receiving party shall not disclose information.",
        "minimum_score": 85,
        "minimum_semantic_score": 100,
    }
    normalized = client.post("/api/search/textual", json=payload).json()
    assert normalized["summary"]["occurrences_total"] == 1
    assert normalized["semantic"]["model"].startswith("Xenova/")
    exact = client.post("/api/search/textual", json={**payload, "mode": "exact"}).json()
    assert exact["summary"]["occurrences_total"] == 0


def test_real_model_budgets_stop_without_partial_scores(real_engine, monkeypatch):
    from traystack.services import semantic
    from traystack.services.textual_matching import SearchTooBroad

    with pytest.raises(SearchTooBroad) as caught:
        real_engine.compare("query", ["word " * 99 + str(index) for index in range(401)])
    assert caught.value.reason == "semantic_token_limit"
    assert not list(real_engine.cache_path.glob("*.json"))
    # Check the deadline after the final inference/cache batch as well as before it.
    real_engine.compare("cached query", ["cached passage"])
    clock = iter([0, 21])
    monkeypatch.setattr(semantic.time, "monotonic", lambda: next(clock))
    with pytest.raises(SearchTooBroad) as caught:
        real_engine.compare("cached query", ["cached passage"])
    assert caught.value.reason == "semantic_time_limit"
    assert caught.value.detail()["results_complete"] is False

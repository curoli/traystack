import pytest
from test_search import indexed

from traystack.services import textual_search
from traystack.services.query_guidance import assess_query
from traystack.services.textual_matching import (
    PassageBudget,
    SearchTooBroad,
    WorkBudget,
    find_passages,
)
from traystack.textual_schemas import TextualAssessmentRequest


def assessment(query, score=80, mode="normalized"):
    return assess_query(TextualAssessmentRequest(query=query, minimum_score=score, mode=mode))


def test_equal_length_budget_uses_exact_arithmetic_and_query_length():
    short, long = assessment("abcdefghij"), assessment("abcdefghij" * 10)
    assert short.equal_length_edit_budget == 2
    assert long.equal_length_edit_budget == 20
    assert "large_edit_budget" not in {row.code for row in short.warnings}
    assert "large_edit_budget" in {row.code for row in long.warnings}
    assert assessment("abcdefghij", 100).equal_length_edit_budget == 0
    assert assessment("a" * 500, 5e-324).equal_length_edit_budget == 499


def test_query_risks_distinguish_names_common_words_numbers_and_normalization():
    assert "short_query_edits" in {row.code for row in assessment("Acme", 80).warnings}
    # Four characters vs five permits one insertion at 80%, even though the
    # equal-length illustration is zero edits. Do not miss this short-name risk.
    assert assessment("Acme", 80).equal_length_edit_budget == 0
    assert "common_words" in {row.code for row in assessment("THE AND NOT", 100).warnings}
    assert "numeric_query" in {row.code for row in assessment("500,000", 95).warnings}
    assert "punctuation_query" in {row.code for row in assessment("---", 100).warnings}
    normalized = assessment("A        n", 85)
    assert normalized.comparison_characters == 3
    assert assessment("A        n", 85, "exact").comparison_characters == 10
    assert normalized.content_characters == 2
    assert assessment("Straße", 90).effective_query == "strasse"


@pytest.mark.integration
def test_assessment_api_matches_executed_search_and_has_no_side_effects(client):
    payload = {"query": "ACME", "minimum_score": 80, "mode": "normalized"}
    before = client.get("/api/documents").json()["total"]
    assessed = client.post("/api/search/textual/assess", json=payload)
    assert assessed.status_code == 200
    result = client.post("/api/search/textual", json=payload)
    assert result.status_code == 200
    assert result.json()["assessment"] == assessed.json()
    assert result.json()["minimum_score"] == 80
    assert client.get("/api/documents").json()["total"] == before
    for endpoint in ["/api/search/textual/assess", "/api/search/textual"]:
        assert client.post(endpoint, json={**payload, "minimum_score": 0}).status_code == 422
        assert client.post(endpoint, json={**payload, "minimum_score": 0.01}).status_code == 200


def test_literal_overflow_stops_before_approximate_comparisons():
    work = WorkBudget(windows=100)
    with pytest.raises(SearchTooBroad) as caught:
        find_passages("target " * 10, "target", 85, work, PassageBudget(document_limit=3))
    error = caught.value
    assert error.reason == "document_passage_limit" and error.observed == 4
    assert work.windows == 100
    assert error.detail()["results_complete"] is False


def test_overlap_windows_count_as_consolidated_passages_not_raw_candidates():
    # Dozens of overlapping candidates describe a single location and must not
    # trip a passage limit of one. Work-budget limits remain independent.
    passages = find_passages(
        "confidentlal information",
        "confidential information",
        70,
        WorkBudget(),
        PassageBudget(document_limit=1),
    )
    assert len(passages) == 1


def test_dense_approximate_passages_abort_after_consolidation():
    with pytest.raises(SearchTooBroad) as caught:
        find_passages(
            "cot " * 12,
            "cat",
            60,
            WorkBudget(),
            PassageBudget(document_limit=100, density_minimum=3, density_limit=20),
        )
    assert caught.value.reason == "dense_passages"
    # Exact wording is allowed through density alone (still subject to count caps).
    assert (
        len(
            find_passages(
                "cat " * 4,
                "cat",
                100,
                WorkBudget(),
                PassageBudget(density_minimum=3, density_limit=20),
            )
        )
        == 4
    )


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["document", "total", "density"])
def test_runtime_abort_returns_no_partial_page_or_success_counts(client, monkeypatch, kind):
    indexed(client, "First", ["target " * 3])
    indexed(client, "Second", ["target " * 3])
    limits = {
        "document": dict(document_limit=2),
        "total": dict(document_limit=100, total_limit=4),
        "density": dict(document_limit=100, density_minimum=2, density_limit=20),
    }[kind]
    monkeypatch.setattr(textual_search, "PassageBudget", lambda: PassageBudget(**limits))
    response = client.post(
        "/api/search/textual", json={"query": "target", "minimum_score": 85, "limit": 1}
    )
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"detail"}
    detail = body["detail"]
    assert detail["code"] == "textual_search_aborted"
    assert detail["results_complete"] is False
    assert detail["documents_inspected"] >= 1
    assert detail["observed_at_least"] > 0
    assert "partial" not in body and "results" not in body and "summary" not in body
    if kind == "total":
        assert detail["documents_inspected"] == 2
        assert detail["observed_at_least"] == 5
    # There is no implicit stricter retry; the exact absence contract stays usable.
    exact = client.post("/api/search", json={"query": "missing", "relation": "lacks"}).json()
    assert exact["total"] == 2


@pytest.mark.integration
def test_narrow_scope_is_echoed_and_result_breadth_has_a_warning(client):
    selected = indexed(client, "Selected", ["target " * 50])
    indexed(client, "Other", ["target"])
    result = client.post(
        "/api/search/textual",
        json={
            "query": "target",
            "minimum_score": 100,
            "document_id": str(selected["document_id"]),
        },
    ).json()
    assert result["document_id"] == str(selected["document_id"])
    assert result["summary"]["documents_total"] == 1
    assert result["summary"]["occurrences_total"] == 50
    assert result["result_warnings"][0]["code"] == "many_passages"

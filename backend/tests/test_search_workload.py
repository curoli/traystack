import importlib
import json
from pathlib import Path

from traystack.services import textual_matching
from traystack.services.normalization import normalize_for_search

ROOT = Path(__file__).resolve().parents[2]


def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    return (
        importlib.import_module("scripts.generate_search_corpus"),
        importlib.import_module("scripts.benchmark_search"),
    )


def test_checked_in_sample_is_reproducible_and_contains_no_derived_private_source(monkeypatch):
    generator, _ = tools(monkeypatch)
    sample = json.loads((ROOT / "examples/search-evaluation/corpus-sample.json").read_text())
    assert generator.generate(8, 3) == sample
    assert "simulated OCR variants are typed errors" in sample["description"]


def test_workload_target_offsets_survive_normalization_and_configuration_is_bounded(monkeypatch):
    generator, _ = tools(monkeypatch)
    corpus = generator.generate()
    assert len(corpus["documents"]) == 64
    for document in corpus["documents"]:
        text = normalize_for_search(document["text"])
        for target in document["targets"].values():
            assert text[target["start"] : target["end"]] == normalize_for_search(target["clause"])
    for count, sections in [(0, 18), (257, 18), (8, -1), (8, 101)]:
        try:
            generator.generate(count, sections)
        except ValueError:
            continue
        raise AssertionError("Invalid workload bounds were accepted")


def test_benchmark_discards_partial_success_on_a_real_passage_limit(monkeypatch):
    _, benchmark = tools(monkeypatch)
    documents = [
        {"id": "first", "text": "target once"},
        {"id": "overflow", "text": "target " * 251},
    ]
    outcome, matches, elapsed = benchmark.run_textual(textual_matching, documents, "target", 100)
    assert outcome["status"] == "aborted"
    assert outcome["detail"]["reason"] == "document_passage_limit"
    assert outcome["detail"]["documents_inspected"] == 2
    assert outcome["detail"]["results_complete"] is False
    assert outcome["passages"] == 0 and matches == []
    assert elapsed >= 0

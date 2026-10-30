"""Evaluate candidate retrieval on training text and previously measured real OCR."""

import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from traystack.services.normalization import normalize_for_search
from traystack.services.textual_matching import (
    CANDIDATE_POLICY,
    SCORER_VERSION,
    WorkBudget,
    find_passages,
)

ROOT = Path(__file__).resolve().parents[1]


def evaluate(rows, thresholds):
    results = []
    for threshold in thresholds:
        details = []
        for row in rows:
            candidates = find_passages(
                normalize_for_search(row["text"]),
                normalize_for_search(row["query"]),
                threshold,
                WorkBudget(),
            )
            top = candidates[0] if candidates else None
            details.append(
                {
                    "id": row["id"],
                    "case": row["case"],
                    "source_literal": row["literal"],
                    "candidate_found": bool(top),
                    "best_score": round(top.score, 4) if top else None,
                    "best_passage": normalize_for_search(row["text"])[
                        top.start : top.end
                    ]
                    if top
                    else None,
                }
            )
        tp = sum(row["source_literal"] and row["candidate_found"] for row in details)
        fn = sum(
            row["source_literal"] and not row["candidate_found"] for row in details
        )
        nonliteral = sum(
            not row["source_literal"] and row["candidate_found"] for row in details
        )
        material = [row for row in details if row["case"] == "counterexample"]
        results.append(
            {
                "threshold": threshold,
                "pairs": len(details),
                "source_literal_recovered": tp,
                "source_literal_missed": fn,
                "nonliteral_candidates": nonliteral,
                "literal_precision_proxy": tp / (tp + nonliteral)
                if tp + nonliteral
                else None,
                "literal_recall": tp / (tp + fn) if tp + fn else None,
                "material_counterexamples_returned": sum(
                    row["candidate_found"] for row in material
                ),
                "material_counterexamples_total": len(material),
                "details": details,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "examples/synthetic-handwriting/ground_truth.json",
    )
    parser.add_argument(
        "--ocr-report",
        type=Path,
        default=ROOT / "examples/synthetic-handwriting/evaluation-train45.json",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/textual-evaluation.json"
    )
    parser.add_argument("--include-details", action="store_true")
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text())
    documents = {row["id"]: row for row in corpus["documents"]}
    measured = json.loads(args.ocr_report.read_text())
    if measured["split"] != "train":
        raise ValueError("This development evaluation uses training data only")
    thresholds = [0, 50, 70, 80, 85, 90, 95, 100]
    clean = [
        {
            "id": row["id"],
            "query": row["query"],
            "text": row["text"],
            "literal": row["expected_normalized_literal"],
            "case": row["case"],
        }
        for row in documents.values()
        if row["split"] == "train"
    ]
    ocr = []
    for row in measured["images"]:
        # Locate the original source using the measured report's stable image ID.
        document_id = row["id"].rsplit("-", 1)[0]
        reference = documents[document_id]
        if reference["split"] != "train" or row["split"] != "train":
            raise ValueError("Mixed evaluation splits")
        ocr.append(
            {
                "id": row["id"],
                "query": reference["query"],
                "text": row["actual_ocr_text"],
                "literal": reference["expected_normalized_literal"],
                "case": reference["case"],
            }
        )
    report = {
        "schema_version": 1,
        "split": "train",
        "scorer_version": SCORER_VERSION,
        "rapidfuzz_version": version("rapidfuzz"),
        "candidate_policy": CANDIDATE_POLICY,
        "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
        "ocr_report_sha256": hashlib.sha256(args.ocr_report.read_bytes()).hexdigest(),
        "scope": "Training development sample only. Actual OCR reused from the measured report; no new OCR or semantic model run. Literal precision is only a proxy: candidate similarity does not establish equivalent meaning.",
        "source_text": evaluate(clean, thresholds),
        "measured_ocr": evaluate(ocr, thresholds),
    }
    if not args.include_details:
        for dataset in ["source_text", "measured_ocr"]:
            for result in report[dataset]:
                details = result.pop("details")
                result["missed_literal_ids"] = [
                    row["id"]
                    for row in details
                    if row["source_literal"] and not row["candidate_found"]
                ]
                result["nonliteral_examples"] = [
                    row
                    for row in details
                    if not row["source_literal"] and row["candidate_found"]
                ][:3]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for name in ["source_text", "measured_ocr"]:
        print(name)
        for result in report[name]:
            print({key: value for key, value in result.items() if key != "details"})
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()

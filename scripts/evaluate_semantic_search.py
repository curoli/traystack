#!/usr/bin/env python3
"""Small synthetic diagnostic set; not a calibrated legal-equivalence benchmark."""

import argparse
import json
from pathlib import Path

from rapidfuzz.distance import Levenshtein
from traystack.services.semantic import SemanticEngine

PAIRS = [
    (
        "identity",
        "The buyer shall pay EUR 500 within thirty days.",
        "The buyer shall pay EUR 500 within thirty days.",
    ),
    (
        "paraphrase",
        "The receiving party shall not disclose confidential information.",
        "The receiving party shall not share confidential information.",
    ),
    (
        "changed_negation",
        "The receiving party shall not disclose confidential information.",
        "The receiving party shall disclose confidential information.",
    ),
    (
        "changed_amount",
        "The buyer shall pay EUR 500 within thirty days.",
        "The buyer shall pay EUR 5000 within thirty days.",
    ),
    (
        "changed_name",
        "Acme Limited shall deliver the goods.",
        "Beta Limited shall deliver the goods.",
    ),
    (
        "changed_deadline",
        "The buyer shall pay within thirty days.",
        "The buyer shall pay within three days.",
    ),
    (
        "unrelated",
        "The receiving party shall not disclose confidential information.",
        "The warehouse opens at nine in the morning.",
    ),
    (
        "german_paraphrase",
        "Der Empfänger darf vertrauliche Informationen nicht weitergeben.",
        "Der Empfänger darf vertrauliche Informationen nicht offenlegen.",
    ),
    (
        "german_changed_negation",
        "Der Käufer muss die Rechnung bezahlen.",
        "Der Käufer muss die Rechnung nicht bezahlen.",
    ),
    (
        "german_changed_amount",
        "Der Käufer zahlt 500 Euro.",
        "Der Käufer zahlt 5000 Euro.",
    ),
]


def evaluate(engine):
    rows = []
    for kind, query, passage in PAIRS:
        # Match the UI's default normalized comparison mode.
        from traystack.services.normalization import normalize_for_search

        left, right = normalize_for_search(query), normalize_for_search(passage)
        score, cosine = engine.compare(left, [right])[0]
        rows.append(
            {
                "case": kind,
                "query": query,
                "passage": passage,
                "textual_score": 100 * Levenshtein.normalized_similarity(left, right),
                "semantic_score": score,
                "cosine": cosine,
            }
        )
    return {
        "description": "Synthetic diagnostic pairs, not held-out evaluation or legal "
        "equivalence labels. Pair scores alone do not assert candidate retrieval.",
        "comparison_mode": "normalized",
        "provenance": engine.provenance(),
        "cases": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--cache", type=Path, default=Path("data/evaluation-embedding-cache")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(SemanticEngine(args.model, args.cache))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(report['cases'])} diagnostic pairs to {args.output}")

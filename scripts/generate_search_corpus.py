"""Author reproducible synthetic contract variants, independent of private source text."""

import argparse
import hashlib
import json
from pathlib import Path

from traystack.services.normalization import normalize_for_search

VERSION = "contract-workload-v1"
MARKER = "EvaluationTenant001"
QUERIES = {
    "confidentiality": f"The receiving party for {MARKER} shall not disclose confidential information.",
    "amount": f"The buyer {MARKER} shall pay EUR 500 within thirty days.",
    "name": f"Acme Limited shall deliver the goods to {MARKER}.",
    "german": f"Der Käufer {MARKER} muss die Rechnung bezahlen.",
}
VARIANTS = {
    "confidentiality": [
        ("identity", QUERIES["confidentiality"]),
        ("changed_negation", QUERIES["confidentiality"].replace("shall not", "shall")),
        ("paraphrase", QUERIES["confidentiality"].replace("disclose", "share")),
        (
            "simulated_ocr",
            QUERIES["confidentiality"]
            .replace("receiving", "receivlng")
            .replace("information", "informatlon"),
        ),
        ("identity", QUERIES["confidentiality"]),
        ("changed_negation", QUERIES["confidentiality"].replace("shall not", "shall")),
        ("unrelated", "The warehouse is open on weekdays during business hours."),
        ("unrelated", "Shipping insurance covers damage while goods are in transit."),
    ],
    "amount": [
        ("identity", QUERIES["amount"]),
        ("changed_amount", QUERIES["amount"].replace("500", "5000")),
        ("changed_deadline", QUERIES["amount"].replace("thirty", "three")),
        ("simulated_ocr", QUERIES["amount"].replace("within", "wlthin")),
    ],
    "name": [
        ("identity", QUERIES["name"]),
        ("changed_name", QUERIES["name"].replace("Acme", "Beta")),
    ],
    "german": [
        ("identity", QUERIES["german"]),
        (
            "changed_negation",
            QUERIES["german"].replace("Rechnung bezahlen", "Rechnung nicht bezahlen"),
        ),
        ("paraphrase", QUERIES["german"].replace("bezahlen", "begleichen")),
        ("simulated_ocr", QUERIES["german"].replace("Rechnung", "Rechnunq")),
    ],
}
BACKGROUND = [
    (
        "Scope of services. Scheduled deliveries follow the order confirmation and the agreed specification. "
        "The supplier records packaging requirements and provides a contact for operational questions."
    ),
    (
        "Inspection. The customer checks quantities after receipt and records visible transport damage. "
        "A discrepancy report identifies the delivery date, affected items and supporting photographs."
    ),
    (
        "Records. Each party retains correspondence concerning an order and its amendments. "
        "Changes to the specification require a written confirmation by the designated representatives."
    ),
    (
        "Term and notices. This framework starts on the date shown in the signature block. "
        "Routine operational messages are sent to the contact addresses maintained by each party."
    ),
    (
        "Force majeure. A party affected by an external disruption informs the other party promptly. "
        "Both parties document the expected duration and discuss reasonable continuity measures."
    ),
    (
        "General provisions. The parties identify applicable schedules by their reference numbers. "
        "An amendment records its effective date and the representatives approving the change."
    ),
]


def generate(count=64, background_sections=18):
    if not 1 <= count <= 256 or not 0 <= background_sections <= 100:
        raise ValueError("Use 1–256 documents and 0–100 background sections")
    documents = []
    for index in range(count):
        sections = [
            f"Synthetic supply agreement {index + 1:03d}. Independently authored evaluation data."
        ]
        for number in range(background_sections):
            sections.append(
                f"Section {number + 1}. "
                + BACKGROUND[(index + number) % len(BACKGROUND)]
            )
        targets = {}
        for family, variants in VARIANTS.items():
            kind, clause = variants[index % len(variants)]
            sections.append(clause)
            targets[family] = {"case": kind, "clause": clause}
        text = "\n\n".join(sections) + "\n"
        normalized = normalize_for_search(text)
        for target in targets.values():
            clause = normalize_for_search(target["clause"])
            start = normalized.index(clause)
            target.update(start=start, end=start + len(clause))
        documents.append(
            {
                "id": f"synthetic-{index + 1:03d}",
                "text": text,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "targets": targets,
            }
        )
    return {
        "schema_version": 1,
        "generator": VERSION,
        "marker": MARKER,
        "description": "Authored synthetic contracts; simulated OCR variants are typed errors, not OCR measurements.",
        "background_sections": background_sections,
        "queries": QUERIES,
        "documents": documents,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--background-sections", type=int, default=18)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = generate(args.count, args.background_sections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(corpus['documents'])} synthetic contracts to {args.output}")

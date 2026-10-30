"""Measure real local OCR against separate ground truth; never substitutes OCR text."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from traystack.config import Settings
from traystack.services.normalization import normalize_for_search
from traystack.services.text_extraction import extract_source


def edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (char != other))
            )
        previous = current
    return previous[-1]


def summarize(rows):
    tp = sum(row["expected_literal"] and row["observed_literal"] for row in rows)
    fp = sum(not row["expected_literal"] and row["observed_literal"] for row in rows)
    fn = sum(row["expected_literal"] and not row["observed_literal"] for row in rows)
    chars = sum(row["reference_characters"] for row in rows)
    return {
        "images": len(rows),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "literal_precision": tp / (tp + fp) if tp + fp else None,
        "literal_recall": tp / (tp + fn) if tp + fn else None,
        "normalized_character_error_rate": sum(row["edit_distance"] for row in rows)
        / chars
        if chars
        else None,
        "warned_positive": sum(row["api_classification"] == "found" for row in rows),
        "unverifiable": sum(
            row["api_classification"] == "unverifiable" for row in rows
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=["train", "dev", "test"], default="train")
    parser.add_argument("--limit", type=int, default=45)
    parser.add_argument(
        "--output", type=Path, default=Path("data/handwriting-evaluation.json")
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    manifest = json.loads(args.manifest.read_text())
    ground_truth = json.loads(
        (args.manifest.parent / manifest["ground_truth_file"]).read_text()
    )
    documents = {document["id"]: document for document in ground_truth["documents"]}
    settings = Settings()
    parameters = {
        "ocr_languages": settings.ocr_languages,
        "ocr_timeout_seconds": settings.ocr_timeout_seconds,
        "ocr_dpi": settings.ocr_dpi,
        "max_pages": settings.processing_max_pages,
        "max_pixels": settings.processing_max_pixels,
        "ocr_min_mean_confidence": 80,
        "requires_manual_review": True,
    }
    rows = []
    versions = {}
    for image in manifest["images"]:
        if image["split"] != args.split:
            continue
        if len(rows) >= args.limit:
            break
        path = (args.manifest.parent / image["file"]).resolve()
        if not path.is_relative_to(args.manifest.parent.resolve()):
            raise ValueError("Image path outside manifest directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != image["sha256"]:
            raise ValueError(f"Image hash mismatch: {path}")
        # Only the source image is supplied to the actual production extractor.
        result = extract_source(path, "image/jpeg", parameters)
        versions = result.processor_versions
        reference = documents[image["document_id"]]
        expected = normalize_for_search(reference["text"])
        observed = result.normalized_text
        found = normalize_for_search(reference["query"]) in observed
        rows.append(
            {
                "id": image["id"],
                "sha256": image["sha256"],
                "font": image["font"],
                "difficulty": image["difficulty"],
                "case": reference["case"],
                "group_id": image["group_id"],
                "split": image["split"],
                "expected_literal": reference["expected_normalized_literal"],
                "observed_literal": found,
                "reference_characters": len(expected),
                "edit_distance": edit_distance(expected, observed),
                "coverage": result.status,
                "quality": result.quality_status,
                "warnings": result.quality_warnings,
                "api_classification": "found" if found else "unverifiable",
                "actual_ocr_text": result.plain_text,
            }
        )
        print(
            f"OCR {len(rows)}: {image['id']} -> {'found' if found else 'unverifiable'}",
            flush=True,
        )
    if not rows:
        raise ValueError("No matching images")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["difficulty"]].append(row)
    report = {
        "schema_version": 1,
        "generator_version": manifest["generator_version"],
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "ground_truth_sha256": hashlib.sha256(
            (args.manifest.parent / manifest["ground_truth_file"]).read_bytes()
        ).hexdigest(),
        "scope": "Font simulation only. No real handwriting, semantic model or legal equivalence evaluated.",
        "split": args.split,
        "selection": f"First {args.limit} matching manifest entries; not a random sample",
        "processor_versions": versions,
        "parameters": parameters,
        "summary": summarize(rows),
        "by_difficulty": {key: summarize(value) for key, value in grouped.items()},
        "images": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    print(f"Measured output: {args.output}")


if __name__ == "__main__":
    main()

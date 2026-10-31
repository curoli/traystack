"""Read-only, bounded mixed-contract benchmark. Run with python -m scripts.benchmark_search."""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import pymupdf
from traystack.services import textual_matching
from traystack.services.normalization import normalize_for_search
from traystack.services.semantic import SemanticEngine
from traystack.services.text_extraction import ProcessingError, extract_source

from scripts.generate_search_corpus import generate

ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = {
    "max_pages": 8,
    "ocr_dpi": 200,
    "max_pixels": 25_000_000,
    "ocr_timeout_seconds": 10,
    "ocr_min_mean_confidence": 80,
    "ocr_languages": "eng",
    "requires_manual_review": True,
}
TYPES = {
    ".txt": "text/plain",
    ".htm": "text/html",
    ".html": "text/html",
    ".pdf": "application/pdf",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def reference(
    ref,
    path="backend/traystack/services/textual_matching.py",
    name="traystack_benchmark_reference",
):
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=ROOT, text=True
    ).strip()
    source = subprocess.check_output(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        text=True,
    )
    # Trusted repository code, explicitly selected by the operator, never document content.
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(  # noqa: S102 — explicit trusted local Git revision, never source-document content
        compile(source, f"git:{revision}:{path}", "exec"), module.__dict__
    )
    return module, revision


def load_sources(roots):
    """Smallest and median eligible file per root/type, no symlinks or source writes."""
    selected, inventory, selection = [], [], []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Missing source root: {root}")
        buckets = {}
        skipped = Counter()
        for path in root.rglob("*"):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in TYPES
            ):
                continue
            # Do not follow a symlinked parent directory outside the supplied root.
            if not path.resolve().is_relative_to(root.resolve()):
                continue
            if path.stat().st_size > 1_000_000:
                skipped["size_limit"] += 1
                continue
            if path.suffix.lower() == ".pdf":
                try:
                    with pymupdf.open(path) as pdf:
                        if (
                            pdf.needs_pass
                            or not 0 < len(pdf) <= PARAMETERS["max_pages"]
                        ):
                            skipped["pdf_page_or_encryption_limit"] += 1
                            continue
                except (RuntimeError, ValueError, pymupdf.FileDataError):
                    skipped["pdf_inspection_failed"] += 1
                    continue
            buckets.setdefault(TYPES[path.suffix.lower()], []).append(path)
        for mime, paths in sorted(buckets.items()):
            paths.sort(key=lambda p: (p.stat().st_size, p.relative_to(root).as_posix()))
            for path in dict.fromkeys([paths[0], paths[len(paths) // 2]]):
                selected.append((path, mime, "local"))
        selection.append(
            {
                "root": root.name,
                "eligible_by_type": {k: len(v) for k, v in buckets.items()},
                "skipped": dict(skipped),
            }
        )
    # Two existing synthetic JPEGs exercise actual OCR, including difficult quality.
    for filename in ["P-printed-scan.jpg", "E-difficult-scan.jpg"]:
        selected.append(
            (
                ROOT / "examples/synthetic-contracts" / filename,
                "image/jpeg",
                "actual_ocr_fixture",
            )
        )
    documents = []
    for index, (path, mime, origin) in enumerate(selected):
        started = time.perf_counter()
        record = {
            "id": f"source-{index + 1:03d}",
            "origin": origin,
            "mime": mime,
            "path": str(path.relative_to(ROOT))
            if path.is_relative_to(ROOT)
            else str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        try:
            parameters = {
                **PARAMETERS,
                "requires_manual_review": origin == "local"
                or path.name.startswith("E-"),
            }
            record["manual_review_requested"] = parameters["requires_manual_review"]
            result = extract_source(path, mime, parameters)
            documents.append(
                {
                    "id": record["id"],
                    "text": result.normalized_text,
                    "origin": origin,
                    "targets": {},
                }
            )
            record.update(
                status=result.status,
                quality=result.quality_status,
                characters=len(result.normalized_text),
                pages=len(result.pages),
                methods=dict(Counter(page.extraction_method for page in result.pages)),
            )
        except ProcessingError as error:
            record.update(status="failed", reason=str(error))
        record["extraction_s"] = time.perf_counter() - started
        inventory.append(record)
        print(
            f"Extracted bounded source {index + 1}/{len(selected)} ({mime}): {record['status']}",
            flush=True,
        )
    return documents, inventory, selection


def run_textual(module, documents, query, minimum):
    budget, passages = module.WorkBudget(), module.PassageBudget()
    matches = []
    started = time.perf_counter()
    outcome = {"status": "complete"}
    for index, document in enumerate(documents):
        if not document["text"].strip():
            continue
        try:
            found = module.find_passages(
                document["text"], query, minimum, budget, passages
            )
        except ValueError as error:
            if not hasattr(error, "detail"):
                raise
            error.documents_inspected = index + 1
            outcome = {"status": "aborted", "detail": error.detail()}
            matches = []  # Never fingerprint or evaluate a partial success list.
            break
        matches.extend((index, item.start, item.end, item.score) for item in found)
    elapsed = time.perf_counter() - started
    outcome.update(
        digest=fingerprint(matches),
        passages=len(matches),
        remaining={
            key: getattr(budget, key) for key in ["characters", "windows", "matches"]
        },
    )
    return outcome, matches, elapsed


def summarize(samples):
    return {
        "samples_s": samples,
        "median_s": statistics.median(samples),
        "min_s": min(samples),
        "max_s": max(samples),
    }


def coverage(documents, family, matches, scores=None):
    rows = {}
    for index, document in enumerate(documents):
        target = document.get("targets", {}).get(family)
        if not target:
            continue
        group = rows.setdefault(
            target["case"], {"documents": 0, "target_overlap": 0, "semantic_scores": []}
        )
        group["documents"] += 1
        for position, (doc, start, end, _) in enumerate(matches):
            overlap = max(0, min(target["end"], end) - max(target["start"], start))
            if doc == index and overlap >= (target["end"] - target["start"]) / 2:
                group["target_overlap"] += 1
                if scores is not None:
                    group["semantic_scores"].append(scores[position][0])
                break
    return rows


def measure_semantic(
    model_path, query, texts, repeats, cache_entries, engine_class=SemanticEngine
):
    if len(texts) > 500:
        return {
            "status": "not_run",
            "reason": "semantic_passage_limit",
            "observed": len(texts),
        }, None
    with tempfile.TemporaryDirectory(prefix="traystack-benchmark-") as directory:
        started = time.perf_counter()
        engine = engine_class(model_path, Path(directory))
        initialization = time.perf_counter() - started
        runtime = engine.session
        calls = []

        def run(*args):
            started = time.perf_counter()
            result = runtime.run(*args)
            calls.append(time.perf_counter() - started)
            return result

        engine.session = SimpleNamespace(run=run)
        started = time.perf_counter()
        try:
            cold = engine.compare(query, texts)
        except ValueError as error:
            return {
                "status": "aborted",
                "reason": type(error).__name__,
                "message": str(error),
            }, None
        cold_s = time.perf_counter() - started
        cold_calls, inference_s = len(calls), sum(calls)
        calls.clear()
        # Directory-size experiment only: placeholders are never treated as valid vectors.
        placeholders = max(0, cache_entries - cold_calls)
        for index in range(placeholders):
            (engine.cache_path / f"placeholder-{index:05d}.json").write_text("null")
        samples = []
        for _ in range(repeats):
            started = time.perf_counter()
            warm = engine.compare(query, texts)
            samples.append(time.perf_counter() - started)
            if warm != cold:
                raise AssertionError("Warm-cache scores changed")
        if calls:
            raise AssertionError("A complete warm cache unexpectedly ran inference")
        return {
            "status": "complete",
            "model_initialization_s": initialization,
            "cold_cache_s": cold_s,
            "cold_inference_calls": cold_calls,
            "cold_inference_s": inference_s,
            "warm_cache": summarize(samples),
            "warm_inference_calls": 0,
            "directory_placeholders": placeholders,
            "cache_entries": placeholders + cold_calls,
            "pipeline": engine.provenance(),
        }, cold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="*", type=Path, default=[])
    parser.add_argument("--reference-ref", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--profiles", nargs="+", type=int, default=[16, 64])
    parser.add_argument("--cache-entries", type=int, default=0)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/performance/report.json"
    )
    parser.add_argument(
        "--private-manifest",
        type=Path,
        default=ROOT / "data/performance/source-manifest.json",
    )
    args = parser.parse_args()
    if (
        not 1 <= args.repeats <= 20
        or not all(1 <= n <= 256 for n in args.profiles)
        or not 0 <= args.cache_entries <= 10_000
    ):
        parser.error(
            "Use 1–20 repeats, 1–256 documents/profile, 0–10,000 cache placeholders"
        )
    if len(args.sources) > 2:
        parser.error("At most two local source roots (two files per root/type)")
    baseline, revision = reference(args.reference_ref)
    baseline_semantic, _ = reference(
        args.reference_ref,
        "backend/traystack/services/semantic.py",
        "traystack_benchmark_semantic_reference",
    )
    sources, inventory, selection = load_sources(
        [root.resolve() for root in args.sources]
    )
    # Raw file paths/hashes remain local. Public report contains aggregates only.
    args.private_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.private_manifest.write_text(
        json.dumps({"selection": selection, "sources": inventory}, indent=2) + "\n"
    )
    report = {
        "schema_version": 1,
        "description": "Single-machine in-process workload measurements; not an SLA or held-out legal benchmark. No DB/HTTP timings included.",
        "reference_revision": revision,
        "implementation_sha256": hashlib.sha256(
            (ROOT / "backend/traystack/services/textual_matching.py").read_bytes()
        ).hexdigest(),
        "semantic_implementation_sha256": hashlib.sha256(
            (ROOT / "backend/traystack/services/semantic.py").read_bytes()
        ).hexdigest(),
        "benchmark_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "rapidfuzz": version("rapidfuzz"),
            "onnxruntime": version("onnxruntime"),
            "tokenizers": version("tokenizers"),
        },
        "selection": selection,
        "extraction": {
            "documents": len(inventory),
            "status": dict(Counter(item["status"] for item in inventory)),
            "quality": dict(
                Counter(item.get("quality", "unavailable") for item in inventory)
            ),
            "total_s": sum(item["extraction_s"] for item in inventory),
            "page_methods": dict(
                sum((Counter(item.get("methods", {})) for item in inventory), Counter())
            ),
        },
        "profiles": [],
    }
    for count in args.profiles:
        corpus = generate(count)
        documents = [
            {
                **doc,
                "text": normalize_for_search(doc["text"]),
                "origin": "authored_synthetic",
            }
            for doc in corpus["documents"]
        ] + sources
        queries = {
            **corpus["queries"],
            "common_confidentiality": "The receiving party shall not disclose confidential information.",
        }
        profile = {
            "synthetic_documents": count,
            "local_and_ocr_documents": len(sources),
            "characters": sum(len(doc["text"]) for doc in documents),
            "searchable_documents": sum(bool(doc["text"].strip()) for doc in documents),
            "corpus_digest": fingerprint(
                [
                    (doc["id"], hashlib.sha256(doc["text"].encode()).hexdigest())
                    for doc in documents
                ]
            ),
            "cases": [],
        }
        for family, phrase in queries.items():
            query = normalize_for_search(phrase)
            runs = {"reference": [], "optimized": []}
            expected = None
            for repeat in range(args.repeats):
                order = [("reference", baseline), ("optimized", textual_matching)]
                if repeat % 2:
                    order.reverse()
                for label, module in order:
                    outcome, matches, elapsed = run_textual(
                        module, documents, query, 85
                    )
                    runs[label].append(elapsed)
                    if expected is None:
                        expected = outcome
                    elif outcome != expected:
                        raise AssertionError(
                            f"Output/budget divergence: {count}/{family}"
                        )
            result = {
                "query_id": family,
                "minimum_score": 85,
                "outcome": outcome,
                "textual": {key: summarize(value) for key, value in runs.items()},
                "speedup": statistics.median(runs["reference"])
                / statistics.median(runs["optimized"]),
            }
            if outcome["status"] == "complete":
                semantic_reports = {}
                reference_values = None
                for label, engine_class in [
                    ("reference", baseline_semantic.SemanticEngine),
                    ("optimized", SemanticEngine),
                ]:
                    semantic, values = measure_semantic(
                        args.model,
                        query,
                        [
                            documents[doc]["text"][start:end]
                            for doc, start, end, _ in matches
                        ],
                        args.repeats,
                        args.cache_entries,
                        engine_class,
                    )
                    semantic_reports[label] = semantic
                    if label == "reference":
                        reference_values = values
                    elif values != reference_values:
                        raise AssertionError(
                            "Semantic scores changed between implementations"
                        )
                result["semantic"] = semantic_reports
                result["synthetic_location_checks"] = coverage(
                    documents, family, matches, values
                )
            profile["cases"].append(result)
            print(
                f"Measured {count} synthetic + {len(sources)} sources / {family}: {outcome['status']}, speedup {result['speedup']:.2f}x",
                flush=True,
            )
        report["profiles"].append(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Aggregate report: {args.output}")


if __name__ == "__main__":
    main()

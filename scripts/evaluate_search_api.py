"""Populate an empty local evaluation stack and measure actual search/review requests."""

import argparse
import hashlib
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from scripts.generate_search_corpus import generate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/performance/api-report.json"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urlparse(base).hostname not in {"localhost", "127.0.0.1"}:
        parser.error(
            "Use a dedicated local evaluation stack; no contract uploads to external hosts"
        )
    if not 8 <= args.count <= 64 or not 1 <= args.repeats <= 10:
        parser.error("Use 8–64 synthetic contracts and 1–10 repeats")

    def request(path, payload=None, content_type="application/json"):
        body = (
            json.dumps(payload).encode()
            if payload is not None and not isinstance(payload, bytes)
            else payload
        )
        headers = {"Content-Type": content_type} if body is not None else {}
        with urlopen(
            Request(base + path, data=body, headers=headers), timeout=60
        ) as response:
            return json.load(response)

    if request("/api/documents?limit=1")["total"] != 0:
        raise ValueError(
            "Use an empty dedicated stack. No existing documents were modified."
        )
    corpus = generate(args.count)
    sources = [
        (item["id"], item["text"].encode(), "text/plain", item["id"] + ".txt", False)
        for item in corpus["documents"]
    ]
    for filename in ["P-printed-scan.jpg", "E-difficult-scan.jpg"]:
        sources.append(
            (
                filename[0],
                (ROOT / "examples/synthetic-contracts" / filename).read_bytes(),
                "image/jpeg",
                filename,
                filename.startswith("E-"),
            )
        )

    def upload(source):
        identity, data, mime, filename, manual = source
        boundary = "traystack-bench-" + uuid.uuid4().hex
        fields = [
            ("title", "Evaluation " + identity),
            ("requires_manual_review", str(manual).lower()),
        ]
        body = b"".join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            for key, value in fields
        )
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        doc = request(
            "/api/documents/upload", body, f"multipart/form-data; boundary={boundary}"
        )
        # Verify the original byte identity before queuing actual extraction/OCR.
        artifact = request(
            f"/api/artifacts/{doc['revisions'][0]['artifacts'][0]['id']}"
        )
        if artifact["sha256"] != hashlib.sha256(data).hexdigest():
            raise AssertionError("Original upload hash mismatch")
        job = request(f"/api/revisions/{doc['revisions'][0]['id']}/process", {})
        return {
            "identity": identity,
            "document_id": doc["id"],
            "revision_id": doc["revisions"][0]["id"],
            "job_id": job["id"],
        }

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        documents = list(pool.map(upload, sources))
    deadline = time.monotonic() + 180
    pending = {item["job_id"] for item in documents}
    while pending:
        for job_id in list(pending):
            status = request(f"/api/jobs/{job_id}")["status"]
            if status == "failed":
                raise AssertionError(
                    "A real processing job failed; no success report was produced"
                )
            if status == "completed":
                pending.remove(job_id)
        if time.monotonic() > deadline:
            raise TimeoutError("Evaluation processing deadline exceeded")
        if pending:
            time.sleep(0.25)
    processing_s = time.perf_counter() - started
    print(
        f"Processed {len(documents)} real uploads/jobs on the dedicated stack",
        flush=True,
    )
    cases = []
    for family, query in corpus["queries"].items():
        payload = {"query": query, "minimum_score": 85}
        textual_samples = []
        for _ in range(args.repeats):
            started = time.perf_counter()
            plain = request("/api/search/textual", payload)
            textual_samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        semantic = request(
            "/api/search/textual", {**payload, "minimum_semantic_score": 0}
        )
        first_s = time.perf_counter() - started
        if semantic["summary"] != plain["summary"]:
            raise AssertionError("Semantic zero changed candidate counts")
        stable = {
            key: semantic[key]
            for key in ["results", "summary", "review_counts", "total", "semantic"]
        }
        warm_samples = []
        for _ in range(args.repeats):
            started = time.perf_counter()
            warm = request(
                "/api/search/textual", {**payload, "minimum_semantic_score": 0}
            )
            warm_samples.append(time.perf_counter() - started)
            if {key: warm[key] for key in stable} != stable:
                raise AssertionError("Warm HTTP search changed result content")
        cases.append(
            {
                "query_id": family,
                "documents_with_matches": semantic["total"],
                "passages": semantic["summary"]["occurrences_total"],
                "textual_samples_s": textual_samples,
                "textual_median_s": statistics.median(textual_samples),
                "first_semantic_request_s": first_s,
                "includes_first_model_initialization": not cases,
                "warm_semantic_samples_s": warm_samples,
                "warm_semantic_median_s": statistics.median(warm_samples),
                "semantic": semantic["semantic"],
            }
        )
        print(
            f"Measured HTTP {family}: textual {statistics.median(textual_samples):.3f}s, warm semantic {statistics.median(warm_samples):.3f}s",
            flush=True,
        )
    first = documents[0]
    payload = {
        "query": corpus["queries"]["confidentiality"],
        "minimum_score": 85,
        "document_id": first["document_id"],
    }
    # Actual source access and state changes after all timed requests.
    source = request(f"/api/revisions/{first['revision_id']}/text")
    if corpus["queries"]["confidentiality"] not in source["plain_text"]:
        raise AssertionError("Source viewer text does not contain the authored clause")
    for decision in ["keep", "dismiss", "later", "unreviewed"]:
        result = request("/api/search/textual", payload)
        doc, item = (
            result["results"][0]["document"],
            result["results"][0]["occurrences"][0],
        )
        saved = request(
            "/api/reviews",
            {
                "occurrence_id": item["occurrence_id"],
                "document_id": doc["document_id"],
                "revision_id": doc["revision_id"],
                "processing_job_id": doc["processing_job_id"],
                "source_artifact_id": doc["artifact_id"],
                "normalization_version": doc["normalization_version"],
                "query": result["query"],
                "mode": result["mode"],
                "scorer_version": result["scorer_version"],
                "candidate_policy": result["candidate_policy"],
                "start_offset": item["start_offset"],
                "end_offset": item["end_offset"],
                "matched_sha256": item["matched_sha256"],
                "expected_version": item["review"]["version"],
                "decision": decision,
            },
        )
        again = request("/api/search/textual", {**payload, "review_filter": decision})
        if again["results"][0]["occurrences"][0]["review"] != saved:
            raise AssertionError("Review state did not persist")
    for family, index, changed in [
        ("amount", 1, "5000"),
        ("name", 1, "Beta"),
        ("confidentiality", 1, "not"),
    ]:
        result = request(
            "/api/search/textual",
            {
                "query": corpus["queries"][family],
                "minimum_score": 85,
                "document_id": documents[index]["document_id"],
            },
        )
        differences = result["results"][0]["occurrences"][0]["differences"]
        if not any(
            piece["kind"] != "equal"
            and changed.casefold()
            in (piece["query_text"] + piece["passage_text"]).casefold()
            for piece in differences
        ):
            raise AssertionError("Material change not visible in comparison")
    printed = next(item for item in documents if item["identity"] == "P")
    ocr = request(
        "/api/search/textual",
        {
            "query": "The receiving party shall not disclose confidential information",
            "minimum_score": 85,
            "document_id": printed["document_id"],
        },
    )
    if ocr["total"] != 1:
        raise AssertionError(
            "Actual printed OCR failed to retrieve its authored clause"
        )
    report = {
        "schema_version": 1,
        "description": "HTTP/DB/model measurements on a fresh dedicated local stack. OS file cache was not reset. No before/after API speedup is claimed.",
        "synthetic_documents": args.count,
        "actual_ocr_documents": 2,
        "upload_and_processing_s": processing_s,
        "cases": cases,
        "workflow": {
            "source_access": True,
            "persisted_decisions": ["keep", "dismiss", "later", "unreviewed"],
            "material_differences_visible": True,
            "actual_printed_ocr_retrieved": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"HTTP report: {args.output}")


if __name__ == "__main__":
    main()

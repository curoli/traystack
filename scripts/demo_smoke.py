"""Exercise the four synthetic fixtures through a running API (stdlib only)."""

import argparse
import hashlib
import json
import mimetypes
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "synthetic-contracts"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    def request(path, data=None, content_type="application/json"):
        headers = {"Content-Type": content_type} if data is not None else {}
        with urlopen(
            Request(base + path, data=data, headers=headers), timeout=40
        ) as response:
            return response.read()

    def get(path):
        return json.loads(request(path))

    def post(path, data):
        return json.loads(request(path, json.dumps(data).encode()))

    require(get("/api/health")["status"] == "ok", "API is not ready")
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    documents = {}
    run_tag = uuid.uuid4().hex[:8]
    for fixture in manifest["fixtures"]:
        content = (FIXTURES / fixture["file"]).read_bytes()
        require(
            hashlib.sha256(content).hexdigest() == fixture["sha256"],
            "Fixture hash mismatch",
        )
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in {
            "title": f"Demo {run_tag} {fixture['id']}",
            "requires_manual_review": str(fixture["requires_manual_review"]).lower(),
        }.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                f"\r\n\r\n{value}\r\n".encode()
            )
        mime = mimetypes.guess_type(fixture["file"])[0]
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{fixture["file"]}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            + content
            + f"\r\n--{boundary}--\r\n".encode()
        )
        document = json.loads(
            request(
                "/api/documents/upload",
                b"".join(parts),
                f"multipart/form-data; boundary={boundary}",
            )
        )
        revision = document["revisions"][0]
        original = revision["artifacts"][0]
        require(
            request(f"/api/artifacts/{original['id']}/content") == content,
            "Downloaded original differs",
        )
        job = post(f"/api/revisions/{revision['id']}/process", {})
        deadline = time.monotonic() + 120
        while True:
            state = get(f"/api/jobs/{job['id']}")
            require(
                state["status"] != "failed",
                f"Processing failed: {state.get('error_message')}",
            )
            if state["status"] == "completed":
                break
            require(time.monotonic() < deadline, f"Worker timeout: {job['id']}")
            time.sleep(0.5)
        selected = get(f"/api/revisions/{revision['id']}/text")
        require(selected["processing_job_id"] == job["id"], "Unexpected selected run")
        detail = get(f"/api/documents/{document['id']}")
        kinds = set()
        for artifact in detail["revisions"][0]["artifacts"]:
            if artifact["kind"] in {"structured_json", "extracted_markdown"}:
                output = request(f"/api/artifacts/{artifact['id']}/content")
                require(bool(output), "Empty derivative")
                if artifact["kind"] == "structured_json":
                    json.loads(output)
                kinds.add(artifact["kind"])
        require(
            kinds == {"structured_json", "extracted_markdown"}, "Missing derivatives"
        )
        documents[fixture["id"]] = document["id"]
        print(
            f"{fixture['id']}: upload, original bytes, processing, text and derivatives OK"
        )

    def search_all(relation, group):
        # Follow independent pagination, so existing library entries cannot hide fixtures.
        offset = 0
        rows = {}
        while True:
            result = post(
                "/api/search",
                {
                    "query": manifest["target_phrase"],
                    "mode": "normalized",
                    "relation": relation,
                    "limit": 100,
                    "offset": offset if group == "results" else 0,
                    "unverifiable_limit": 100,
                    "unverifiable_offset": offset if group == "unverifiable" else 0,
                },
            )
            rows.update({row["document_id"]: row for row in result[group]})
            total = result["total" if group == "results" else "unverifiable_total"]
            offset += 100
            if offset >= total:
                return rows

    positives = search_all("contains", "results")
    negatives = search_all("lacks", "results")
    unknown = search_all("lacks", "unverifiable")
    for key in ("A", "P"):
        row = positives.get(documents[key], {})
        require(row.get("status") == "found", f"{key}: missing positive match")
        require(
            row.get("page_number") == 1 and bool(row.get("snippet")), "Missing evidence"
        )
        require(documents[key] not in negatives, f"{key}: false negative suggestion")
    require(documents["D"] not in positives, "D: unexpected positive match")
    require(
        negatives.get(documents["D"], {}).get("status")
        == "not_found_in_processed_text",
        "D: expected negative result",
    )
    require(
        documents["E"] not in negatives, "E: review input became a negative suggestion"
    )
    require(
        unknown.get(documents["E"], {}).get("status") == "unverifiable",
        "E: expected unverifiable result",
    )
    print(f"Demo {run_tag}: A/P found, D negative, E unverifiable. All checks passed.")
    print("Synthetic documents remain available in the UI; no data was deleted.")


if __name__ == "__main__":
    main()

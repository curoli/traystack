"""Import local files or a generated image manifest through the real TrayStack API."""

import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Match the server's extension-based source interpretation, including aliases.
SOURCE_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain",
    ".htm": "text/html",
    ".html": "text/html",
}
SUPPORTED = set(SOURCE_TYPES)


def inputs(source: Path):
    if source.is_file() and source.suffix == ".json":
        manifest = json.loads(source.read_text())
        for image in manifest["images"]:
            path = (source.parent / image["file"]).resolve()
            if not path.is_relative_to(source.parent.resolve()):
                raise ValueError("Manifest file must stay within its directory")
            yield path, image
    elif source.is_file():
        yield source, {}
    elif source.is_dir():
        for path in sorted(source.rglob("*")):
            if (
                path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in SUPPORTED
            ):
                yield path, {}
    else:
        raise ValueError(f"Input not found: {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="File, directory or generated manifest.json"
    )
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument(
        "--limit", type=int, default=20, help="Maximum files per invocation"
    )
    parser.add_argument(
        "--process", action="store_true", help="Queue and wait for real processing"
    )
    parser.add_argument("--manual-review", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Inspect selection without uploading"
    )
    parser.add_argument(
        "--receipts", type=Path, default=Path("data/import-receipts.json")
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    base = args.base_url.rstrip("/")
    receipts = json.loads(args.receipts.read_text()) if args.receipts.exists() else {}

    def request(path, data=None, content_type="application/json"):
        headers = {"Content-Type": content_type} if data is not None else {}
        with urlopen(
            Request(base + path, data=data, headers=headers), timeout=40
        ) as response:
            return json.load(response)

    def save_receipts():
        args.receipts.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.receipts.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipts, indent=2) + "\n")
        temporary.replace(args.receipts)

    def process(document):
        revision = document["revisions"][0]
        # The receipt may refer to a previous queued/failed or completed run.
        if revision["processing_status"] == "completed":
            return
        active = next(
            (job for job in revision["jobs"] if job["status"] in {"queued", "running"}),
            None,
        )
        job = active or request(f"/api/revisions/{revision['id']}/process", b"{}")
        deadline = time.monotonic() + 180
        while True:
            state = request(f"/api/jobs/{job['id']}")
            if state["status"] == "completed":
                return
            if state["status"] == "failed":
                raise RuntimeError(
                    f"Processing failed: {state['error_message']} (job {job['id']})"
                )
            if time.monotonic() > deadline:
                raise TimeoutError(f"Processing still pending: job {job['id']}")
            time.sleep(0.5)

    count = 0
    for path, info in inputs(args.source):
        if count >= args.limit:
            break
        if path.suffix.lower() not in SUPPORTED:
            raise ValueError(f"Unsupported file type: {path}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if info.get("sha256", digest) != digest:
            raise ValueError(f"Manifest hash mismatch: {path}")
        manual = args.manual_review or info.get("requires_manual_review", False)
        source_type = SOURCE_TYPES[path.suffix.lower()]
        # Equal bytes can require different extraction/quality rules (TXT vs HTML).
        # Do not reuse legacy untyped receipts: their processing type is ambiguous.
        key = f"v2|{base}|{source_type}|{digest}|manual={bool(manual)}"
        count += 1
        if args.dry_run:
            print(f"Would import {path} sha256={digest} manual_review={bool(manual)}")
            continue
        document = None
        if key in receipts:
            try:
                document = request(f"/api/documents/{receipts[key]}")
            except HTTPError as error:
                if error.code != 404:
                    raise
        reused = document is not None
        if document is None:
            boundary = uuid.uuid4().hex
            metadata = {
                "import_source": str(path),
                "import_sha256": digest,
                "provenance": "font-based-simulation"
                if info
                else "user-provided-local-source",
                **{
                    field: info[field]
                    for field in ["group_id", "split", "difficulty"]
                    if field in info
                },
            }
            fields = {
                "title": info.get("id", path.stem)[:300],
                "metadata": json.dumps(metadata),
                "requires_manual_review": str(bool(manual)).lower(),
            }
            body = b"".join(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                f"\r\n\r\n{value}\r\n".encode()
                for name, value in fields.items()
            )
            body += (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{path.name}"\r\nContent-Type: {source_type}\r\n\r\n'.encode()
                + data
                + f"\r\n--{boundary}--\r\n".encode()
            )
            document = request(
                "/api/documents/upload",
                body,
                f"multipart/form-data; boundary={boundary}",
            )
            receipts[key] = document["id"]
            save_receipts()  # Persist before processing, so a timeout can be resumed safely.
        if args.process:
            process(document)
        print(
            f"{'Reused' if reused else 'Imported'} {path.name}: {document['id']}",
            flush=True,
        )
    if not count:
        raise ValueError("No supported inputs found")
    print(f"Selected {count} files. Source bytes were not changed.")


if __name__ == "__main__":
    main()

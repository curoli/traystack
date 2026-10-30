"""Inventory local source bytes without modifying or redistributing their content."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def inventory(roots: list[Path]) -> dict:
    records = []
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Source directory not found: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            encoding = None
            if path.suffix.lower() in {".txt", ".htm", ".html"}:
                try:
                    data.decode("utf-8-sig")
                    encoding = "utf-8-sig"
                except UnicodeDecodeError:
                    encoding = "unsupported"
            records.append(
                {
                    "root": str(root),
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "extension": path.suffix.lower(),
                    "encoding": encoding,
                    "provenance": "user-provided-local-source",
                    "license": "not-supplied",
                    "redistribution_verified": False,
                }
            )
    hashes = Counter(record["sha256"] for record in records)
    return {
        "schema_version": 1,
        "scope": "Local inventory only; directory names do not establish dataset origin or license.",
        "summary": {
            "files": len(records),
            "size_bytes": sum(record["size_bytes"] for record in records),
            "extensions": dict(
                sorted(Counter(record["extension"] for record in records).items())
            ),
            "unique_byte_contents": len(hashes),
            "duplicate_files": sum(count - 1 for count in hashes.values()),
        },
        "sources": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    print(f"Local inventory: {args.output}")


if __name__ == "__main__":
    main()

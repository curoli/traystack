"""Explicit build/setup download; runtime inference only uses verified local files."""

import argparse
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from traystack.ocr_model import ARTIFACTS, MODEL_ID, verify


def prepare(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ARTIFACTS.items():
        import hashlib

        if (root / name).exists() and hashlib.sha256(
            (root / name).read_bytes()
        ).hexdigest() == expected:
            continue
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.urlopen(url, timeout=120) as source:
                    while block := source.read(1024 * 1024):
                        output.write(block)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise ValueError("ocr_model_integrity_failed")
            temporary.chmod(0o644)
            os.replace(temporary, root / name)
        finally:
            temporary.unlink(missing_ok=True)
    verify(root)
    shutil.copyfile(Path(__file__).with_name("model_license.txt"), root / "LICENSE.txt")
    (root / "MODEL.json").write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "upstream": "https://github.com/PaddlePaddle/PaddleOCR",
                "conversion": "https://github.com/RapidAI/RapidOCR",
                "license": "Apache-2.0",
                "artifacts": ARTIFACTS,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    prepare(parser.parse_args().directory)

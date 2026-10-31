"""Explicit setup command, never imported by search request handling."""

import argparse
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from traystack.semantic_model import (
    ARTIFACTS,
    MODEL_ID,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    verify_artifacts,
)


def prepare(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    for name, (remote, _) in ARTIFACTS.items():
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as target:
            temporary = Path(target.name)
        try:
            url = f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{remote}"
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output)
            temporary.chmod(0o644)
            os.replace(temporary, root / name)
        finally:
            temporary.unlink(missing_ok=True)
    verify_artifacts(root)
    shutil.copyfile(Path(__file__).with_name("model_license.txt"), root / "LICENSE.txt")
    (root / "MODEL.txt").write_text(
        f"{MODEL_ID}\nQuantized ONNX conversion by Xenova.\n"
        "Base: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2\n"
        "License: Apache-2.0; see https://www.apache.org/licenses/LICENSE-2.0\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    prepare(parser.parse_args().directory)

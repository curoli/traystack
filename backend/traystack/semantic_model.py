"""Pinned model artifacts and pipeline identity; downloads happen only during setup."""

import hashlib
from pathlib import Path

MODEL_REPOSITORY = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "2c4055b12046f11709e9df2c122e59ffbdc2f900"
MODEL_ID = f"{MODEL_REPOSITORY}@{MODEL_REVISION}"
PIPELINE_VERSION = "minilm-int8-singleton-masked-mean-l2-128-v2"
SCORE_VERSION = "positive-cosine-exact-100-v1"
ARTIFACTS = {
    "model.onnx": (
        "onnx/model_quantized.onnx",
        "66fc00f5f29afcaff34092e1bdd20008ca3918265a82fb9695a551e510cc4ebc",
    ),
    "tokenizer.json": (
        "tokenizer.json",
        "b60b6b43406a48bf3638526314f3d232d97058bc93472ff2de930d43686fa441",
    ),
}
MAX_TOKENS = 128


def verify_artifacts(root: Path):
    for name, (_, expected) in ARTIFACTS.items():
        with (root / name).open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Unexpected semantic model artifact: {name}")

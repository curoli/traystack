"""Pinned PaddleOCR PP-OCRv6 small ONNX models, deployed through RapidOCR."""

import hashlib
from pathlib import Path

MODEL_ID = "PP-OCRv6-small-rapidocr-3.10.0"
ROOT_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6"
ARTIFACTS = {
    "det.onnx": (
        f"{ROOT_URL}/det/PP-OCRv6_det_small.onnx",
        "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    ),
    "rec.onnx": (
        f"{ROOT_URL}/rec/PP-OCRv6_rec_small.onnx",
        "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    ),
}


def verify(root: Path):
    for name, (_, expected) in ARTIFACTS.items():
        with (root / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("ocr_model_integrity_failed")

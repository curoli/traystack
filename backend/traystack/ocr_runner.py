"""Isolated, CPU-only OCR invocation. The parent enforces a hard process timeout."""

import json
import sys
from pathlib import Path

from traystack.ocr_model import verify


def recognize(image_path: str, root: Path):
    verify(root)
    import onnxruntime
    from rapidocr import ModelType, OCRVersion, RapidOCR

    onnxruntime.disable_telemetry_events()

    engine = RapidOCR(
        params={
            "Global.use_cls": False,
            "Global.text_score": 0.0,
            "Global.log_level": "critical",
            "Det.model_path": str(root / "det.onnx"),
            "Rec.model_path": str(root / "rec.onnx"),
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
            "Det.model_type": ModelType.SMALL,
            "Rec.model_type": ModelType.SMALL,
            "EngineConfig.onnxruntime.intra_op_num_threads": 2,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
    )
    from traystack.ocr_detection import observe_detection

    detection = observe_detection(engine)
    result = engine(image_path)
    lines = (
        []
        if result.txts is None
        else [
            {"text": text, "confidence": float(score) * 100, "polygon": box.tolist()}
            for text, score, box in zip(result.txts, result.scores, result.boxes, strict=True)
        ]
    )
    return {
        "lines": lines,
        "detection_limit_hit": detection.limit_hit,
        "raw_contours": detection.raw_contours,
    }


if __name__ == "__main__":
    # Write only structured output to a dedicated file; library logging is never parsed.
    Path(sys.argv[3]).write_text(
        json.dumps(recognize(sys.argv[1], Path(sys.argv[2])), allow_nan=False)
    )

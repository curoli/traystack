"""Integration checks, not handwriting accuracy evaluation."""

import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from traystack.ocr_model import MODEL_ID, verify
from traystack.services import text_extraction


def parameters():
    return dict(
        ocr_backend="paddleocr", ocr_model=MODEL_ID, max_pixels=25_000_000, ocr_timeout_seconds=30
    )


def test_adapter_preserves_lines_geometry_and_engine_identity(monkeypatch):
    def run(command, **kwargs):
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "detection_limit_hit": False,
                    "raw_contours": 1,
                    "lines": [
                        dict(
                            text="Payment shall not change",
                            confidence=95,
                            polygon=[[1, 2], [50, 2], [50, 10], [1, 10]],
                        )
                    ],
                }
            )
        )
        assert kwargs["timeout"] == 30 and kwargs["check"]

    monkeypatch.setattr(text_extraction.subprocess, "run", run)
    page = text_extraction.ocr_page(Image.new("RGB", (100, 100)), 1, parameters())
    assert page.text == "Payment shall not change"
    assert page.layout_metadata["model"] == MODEL_ID
    assert page.layout_metadata["lines"][0]["polygon"][0] == [1, 2]
    assert page.confidence == 95 and not page.quality_warnings
    assert "words" not in page.layout_metadata  # Line boxes must not pretend to be word boxes.


@pytest.mark.parametrize(
    "error,reason",
    [
        (subprocess.TimeoutExpired("ocr", 30), "ocr_timeout"),
        (subprocess.CalledProcessError(1, "SECRET"), "ocr_failed"),
    ],
)
def test_failures_never_publish_empty_success(monkeypatch, error, reason):
    def fail(*a, **kw):
        raise error

    monkeypatch.setattr(text_extraction.subprocess, "run", fail)
    page = text_extraction.ocr_page(Image.new("RGB", (100, 100)), 1, parameters())
    assert page.status == "unavailable" and page.quality_warnings == [reason]
    assert "SECRET" not in str(page)


def test_missing_model_fails_before_any_inference_or_download(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify(tmp_path)


@pytest.mark.integration
@pytest.mark.ocr
def test_real_paddle_job_uses_default_backend_and_local_models(client, monkeypatch):
    from test_pipeline import PHRASE, enqueue, run_worker, selected_text, upload

    root = Path(__file__).resolve().parents[2] / "data/models/paddleocr-small"
    if not root.exists():
        pytest.skip(
            "Prepare OCR models with python -m traystack.prepare_ocr_model "
            "data/models/paddleocr-small"
        )
    monkeypatch.setenv("OCR_MODEL_PATH", str(root))
    client.app.state.settings.ocr_backend = "paddleocr"
    doc = upload(client, "P-printed-scan.jpg")
    job = enqueue(client, doc)
    assert job["parameters"]["ocr_backend"] == "paddleocr"
    assert run_worker(client)
    result = selected_text(client, doc)
    assert result["status"] == "complete"
    assert PHRASE in result["normalized_text"]
    assert result["pages"][0]["layout_metadata"]["lines"]
    finished = client.get(f"/api/jobs/{job['id']}").json()
    assert finished["processor_versions"]["ocr_model"] == MODEL_ID


@pytest.mark.parametrize("count", [999, 1000, 1001])
def test_raw_contour_overflow_is_detected_before_small_box_filtering(count):
    import numpy as np

    from traystack.ocr_detection import LimitAwarePostProcess

    bitmap = np.zeros((330, 330), dtype=np.uint8)
    for index in range(count):
        y, x = divmod(index, 32)
        # OpenCV visits the last (bottom-most) contour first: it is rejected by size.
        size = 2 if index == count - 1 else 6
        bitmap[y * 10 : y * 10 + size, x * 10 : x * 10 + size] = 1
    detector = LimitAwarePostProcess(max_candidates=1000, box_thresh=0.5)
    boxes, _ = detector.boxes_from_bitmap(bitmap.astype(float), bitmap, 330, 330)
    assert detector.raw_contours == count
    assert len(boxes) == min(count, 1000) - 1
    assert detector.limit_hit is (count > 1000)


@pytest.mark.integration
@pytest.mark.parametrize("line_count", [0, 999])
def test_truncated_detection_never_enters_ready_search(client, monkeypatch, line_count):
    from test_pipeline import enqueue, run_worker, selected_text, upload

    original_run = subprocess.run

    def run(command, **kwargs):
        if command[1:3] != ["-m", "traystack.ocr_runner"]:
            return original_run(command, **kwargs)
        Path(command[-1]).write_text(
            json.dumps(
                {
                    "lines": [
                        dict(
                            text="The payment clause remains unchanged",
                            confidence=99,
                            polygon=[[1, 2], [50, 2], [50, 10], [1, 10]],
                        )
                    ]
                    * line_count,
                    "detection_limit_hit": True,
                    "raw_contours": 1001,
                }
            )
        )

    monkeypatch.setattr(text_extraction.subprocess, "run", run)
    client.app.state.settings.ocr_backend = "paddleocr"
    doc = upload(client, "P-printed-scan.jpg")
    enqueue(client, doc)
    assert run_worker(client)
    result = selected_text(client, doc)
    assert result["quality_status"] == "needs_review"
    assert "ocr_detection_limit" in result["quality_warnings"]
    page = result["pages"][0]
    assert page["layout_metadata"]["raw_contours"] == 1001
    assert page["layout_metadata"]["detection_limit_hit"] is True
    response = client.post(
        "/api/search/textual",
        json={
            "query": "payment clause",
            "minimum_score": 100,
            "ready_only": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["documents_searched"] == 0


def test_example_environment_has_unique_active_keys():
    source = Path(__file__).resolve().parents[2] / ".env.example"
    keys = [
        line.split("=", 1)[0]
        for line in source.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(keys) == len(set(keys))
    assert keys.count("OCR_BACKEND") == keys.count("OCR_LANGUAGES") == 1

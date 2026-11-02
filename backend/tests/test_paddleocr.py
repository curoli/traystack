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
                [
                    dict(
                        text="Payment shall not change",
                        confidence=95,
                        polygon=[[1, 2], [50, 2], [50, 10], [1, 10]],
                    )
                ]
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

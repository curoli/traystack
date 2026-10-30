import hashlib
import io
import json
import runpy
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from traystack.services.processing import run_once

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
@pytest.mark.parametrize("order", [("txt", "html"), ("html", "txt")])
def test_import_receipts_preserve_processing_type_in_both_orders(
    client, tmp_path, monkeypatch, order
):
    # Run the real importer against the real API and worker, bridging only HTTP transport.
    # This exercises saved receipts across invocations without a separate TCP server.
    importer = runpy.run_path(str(ROOT / "scripts/import_examples.py"))["main"]
    receipts = tmp_path / "receipts.json"
    raw = b"The receiving party shall not disclose confidential <b>information</b>."

    def urlopen(request, timeout):
        path = urlsplit(request.full_url).path
        if path.startswith("/api/jobs/") and request.get_method() == "GET":
            run_once(client.app.state.session_factory, client.app.state.storage)
        response = client.request(
            request.get_method(), path, content=request.data, headers=request.headers
        )
        assert response.is_success, response.text
        return io.BytesIO(response.content)

    monkeypatch.setitem(importer.__globals__, "urlopen", urlopen)
    for extension in order:
        source = tmp_path / f"same.{extension}"
        source.write_bytes(raw)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "import_examples.py",
                str(source),
                "--process",
                "--receipts",
                str(receipts),
            ],
        )
        importer()
        importer()  # Same format must still reuse its own document.
        if extension == order[0]:
            # Old untyped receipts must never alias the next import to this source.
            saved = json.loads(receipts.read_text())
            saved[f"http://localhost:8080|{hashlib.sha256(raw).hexdigest()}|manual=False"] = (
                client.get("/api/documents").json()["items"][0]["id"]
            )
            receipts.write_text(json.dumps(saved))

    # Uppercase extension and HTML's .htm alias must still reuse the HTML import.
    alias = tmp_path / "same.HTM"
    alias.write_bytes(raw)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "import_examples.py",
            str(alias),
            "--process",
            "--receipts",
            str(receipts),
        ],
    )
    importer()

    documents = client.get("/api/documents").json()
    assert documents["total"] == 2
    artifacts = {
        next(
            artifact
            for artifact in document["revisions"][0]["artifacts"]
            if artifact["kind"] == "original"
        )["mime_type"]: document
        for document in documents["items"]
    }
    assert set(artifacts) == {"text/plain", "text/html"}
    assert len(set(json.loads(receipts.read_text()).values())) == 2
    text = {}
    for mime, document in artifacts.items():
        revision = document["revisions"][0]
        text[mime] = client.get(f"/api/revisions/{revision['id']}/text").json()
    assert text["text/plain"]["quality_status"] == "no_known_issue"
    assert text["text/html"]["quality_status"] == "needs_review"
    assert "html_requires_review" in text["text/html"]["quality_warnings"]
    assert "confidential information" in text["text/html"]["normalized_text"]
    result = client.post(
        "/api/search",
        json={
            "query": "confidential information",
            "relation": "lacks",
        },
    ).json()
    assert [row["document_id"] for row in result["results"]] == [artifacts["text/plain"]["id"]]
    positive = client.post("/api/search", json={"query": "confidential information"}).json()
    assert [row["document_id"] for row in positive["results"]] == [artifacts["text/html"]["id"]]

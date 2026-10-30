import hashlib

import pytest

from traystack.services.processing import run_once
from traystack.services.text_documents import decode_text, html_text


def test_html_reading_keeps_inline_words_and_block_boundaries():
    assert (
        html_text(
            "<html><head><title>Ignore me</title></head>"
            "<body><p>Con<b>fidential</b> &amp; private</p>"
            '<script>alert("must not run")</script><style>.hidden{}</style>'
            "<template>not rendered</template><div>Second<br/>line</div></body></html>"
        )
        == "Confidential & private\nSecond\nline"
    )


@pytest.mark.parametrize("data", [b"\xff\xfe", b"\x00binary", b"\x1b[31m", b" \r\n\t"])
def test_text_decoding_refuses_ambiguous_binary_or_empty_inputs(data):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        decode_text(data)


@pytest.mark.integration
@pytest.mark.parametrize(
    "filename,raw,expected,review",
    [
        (
            "terms.txt",
            b"\xef\xbb\xbfThe receiving party shall not disclose confidential information.\r\nEnd.",
            "The receiving party shall not disclose confidential information.\r\nEnd.",
            False,
        ),
        (
            "terms.htm",
            b"<p>The receiving party shall not disclose <b>confidential</b> information.</p>"
            b'<script>window.unwanted = true;</script><img src="https://invalid.example/private.jpg">',
            "The receiving party shall not disclose confidential information.",
            True,
        ),
        (
            "terms.html",
            b'<p>Delivery terms only.</p><img alt="Confidential clause" src="missing.jpg">',
            "Delivery terms only.",
            True,
        ),
    ],
)
def test_text_upload_process_search_download_with_conservative_html(
    client, filename, raw, expected, review
):
    response = client.post(
        "/api/documents/upload", data={"title": "Text source"}, files={"file": (filename, raw)}
    )
    assert response.status_code == 201, response.text
    document = response.json()
    revision = document["revisions"][0]
    artifact = revision["artifacts"][0]
    assert artifact["sha256"] == hashlib.sha256(raw).hexdigest()
    assert client.get(f"/api/artifacts/{artifact['id']}/content").content == raw
    assert client.post(f"/api/revisions/{revision['id']}/process", json={}).status_code == 202
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    text = client.get(f"/api/revisions/{revision['id']}/text").json()
    assert text["plain_text"] == expected
    assert text["pages_total"] == 1
    assert text["pages"][0]["extraction_method"] == ("html_text" if review else "plain_text")
    assert text["pages"][0]["layout_metadata"]["physical_page"] is False
    assert text["quality_status"] == ("needs_review" if review else "no_known_issue")
    assert ("html_requires_review" in text["quality_warnings"]) is review
    # A trusted TXT can be negative. HTML must remain unverifiable, even if the
    # visible extracted text is long and all logical sections were processed.
    result = client.post("/api/search", json={"query": "absent clause", "relation": "lacks"}).json()
    assert len(result["unverifiable"]) == int(review)
    assert len(result["results"]) == int(not review)
    if "shall not disclose" in expected:
        positive = client.post("/api/search", json={"query": "shall not disclose"}).json()
        assert positive["results"][0]["document_id"] == document["id"]
        assert ("html_requires_review" in positive["results"][0]["warnings"]) is review
    assert "window.unwanted" not in text["plain_text"]


@pytest.mark.integration
@pytest.mark.parametrize("raw", [b"\xffbroken", b"\x00binary", b" \n"])
def test_invalid_text_upload_leaves_no_document(client, raw):
    response = client.post(
        "/api/documents/upload", data={"title": "Bad text"}, files={"file": ("bad.txt", raw)}
    )
    assert response.status_code == 422
    assert client.get("/api/documents").json()["total"] == 0


@pytest.mark.integration
def test_html_with_only_unread_image_content_cannot_be_negative(client):
    response = client.post(
        "/api/documents/upload",
        data={"title": "Image HTML"},
        files={
            "file": ("scan.html", b'<html><script>hidden()</script><img src="contract.jpg"></html>')
        },
    )
    revision = response.json()["revisions"][0]
    client.post(f"/api/revisions/{revision['id']}/process", json={})
    assert run_once(client.app.state.session_factory, client.app.state.storage)
    result = client.post("/api/search", json={"query": "clause", "relation": "lacks"}).json()
    assert result["total"] == 0 and result["unverifiable_total"] == 1
    assert result["unverifiable"][0]["coverage"] == "unavailable"

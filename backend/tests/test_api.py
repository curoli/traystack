import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

FIXTURES = Path(__file__).resolve().parents[2] / "examples" / "synthetic-contracts"
pytestmark = pytest.mark.integration


def upload(client, filename="A-confidentiality.pdf", **data):
    return client.post(
        "/api/documents/upload",
        data={"title": "Demo contract", **data},
        files={"file": (filename, (FIXTURES / filename).read_bytes(), "application/octet-stream")},
    )


@pytest.mark.parametrize(
    "filename",
    ["A-confidentiality.pdf", "D-delivery.pdf", "P-printed-scan.jpg", "E-difficult-scan.jpg"],
)
def test_upload_list_detail_and_byte_identical_download(client, filename):
    response = upload(
        client, filename, metadata='{"company":"Example"}', requires_manual_review="true"
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["metadata"] == {"company": "Example"}
    revision = document["revisions"][0]
    artifact = revision["artifacts"][0]
    assert len({document["id"], revision["id"], artifact["id"]}) == 3
    assert revision["processing_status"] == "not_processed"
    assert artifact["revision_id"] == revision["id"]
    assert artifact["parameters"]["requires_manual_review"] is True
    assert "storage_key" not in artifact
    original = (FIXTURES / filename).read_bytes()
    download = client.get(f"/api/artifacts/{artifact['id']}/content")
    assert download.status_code == 200
    assert download.content == original
    assert artifact["sha256"] == hashlib.sha256(original).hexdigest()
    assert artifact["size_bytes"] == len(original)
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/documents/{document['id']}").json() == document
    assert client.get(f"/api/revisions/{revision['id']}").json() == revision
    assert client.get(f"/api/artifacts/{artifact['id']}").json() == artifact
    page = client.get("/api/documents?limit=1&offset=0").json()
    assert page["total"] == 1 and page["items"] == [document]
    assert client.get("/api/documents?offset=1").json()["items"] == []
    assert client.get("/api/health").status_code == 200


def test_deduplicated_bytes_keep_independent_metadata(client):
    first, second = upload(client).json(), upload(client).json()
    a = first["revisions"][0]["artifacts"][0]
    b = second["revisions"][0]["artifacts"][0]
    assert a["id"] != b["id"] and a["sha256"] == b["sha256"]
    assert len(list(client.app.state.storage.root.glob("*/*/*"))) == 1


@pytest.mark.parametrize(
    "metadata", ["[]", "null", "broken", '{"x":"\\u0000"}', '{"x":NaN}', '{"x":"\\ud800"}']
)
def test_invalid_metadata_creates_no_document(client, metadata):
    assert upload(client, metadata=metadata).status_code == 422
    assert client.get("/api/documents").json()["total"] == 0


@pytest.mark.parametrize(
    "filename,content",
    [
        ("fake.pdf", b"not a PDF"),
        ("malware.exe", b"MZ"),
        ("empty.pdf", b""),
        ("fake.jpg", b"%PDF-1.4\n"),
        ("bad.pdf", b"%PDF-1.4\nbroken"),
    ],
)
def test_unsupported_or_invalid_file(client, filename, content):
    response = client.post(
        "/api/documents/upload", data={"title": "Test"}, files={"file": (filename, content)}
    )
    assert response.status_code == 422
    assert client.get("/api/documents").json()["total"] == 0


def test_upload_limit_and_whitespace_title(client):
    response = client.post(
        "/api/documents/upload",
        data={"title": "Test"},
        files={"file": ("large.pdf", b"x" * (1024 * 1024 + 1))},
    )
    assert response.status_code == 413
    assert upload(client, title="   ").status_code == 422


def test_unsafe_filename_and_sql_like_title_are_plain_data(client):
    raw = (FIXTURES / "A-confidentiality.pdf").read_bytes()
    response = client.post(
        "/api/documents/upload",
        data={"title": "Robert'); DROP TABLE documents;--"},
        files={"file": ("../../contract.pdf", raw)},
    )
    assert response.status_code == 201
    artifact = response.json()["revisions"][0]["artifacts"][0]
    assert artifact["original_filename"] == "contract.pdf"
    assert client.get("/api/documents").json()["total"] == 1


def test_missing_and_invalid_identifiers_and_pagination(client):
    for path in ["documents", "revisions", "artifacts"]:
        assert client.get(f"/api/{path}/{uuid4()}").status_code == 404
        assert client.get(f"/api/{path}/bad-id").status_code == 422
    assert client.get(f"/api/artifacts/{uuid4()}/content").status_code == 404
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert client.get(f"/api/documents?{query}").status_code == 422


def test_missing_blob_is_visible_as_unavailable(client):
    artifact = upload(client).json()["revisions"][0]["artifacts"][0]
    for path in client.app.state.storage.root.glob("*/*/*"):
        path.unlink()
    assert client.get(f"/api/artifacts/{artifact['id']}/content").status_code == 503


def test_foreign_keys_uniqueness_and_source_revision_invariant(client, engine):
    first, second = upload(client).json(), upload(client).json()
    revision = first["revisions"][0]
    artifact = revision["artifacts"][0]
    other_revision = second["revisions"][0]["id"]
    statements = [
        (
            "INSERT INTO revisions (id,document_id,revision_number) VALUES (:id,:document,1)",
            {"id": uuid4(), "document": first["id"]},
        ),
        (
            "INSERT INTO revisions (id,document_id,revision_number) VALUES (:id,:document,0)",
            {"id": uuid4(), "document": first["id"]},
        ),
        (
            "UPDATE artifacts SET revision_id = :revision WHERE id = :id",
            {"revision": uuid4(), "id": artifact["id"]},
        ),
        (
            "UPDATE artifacts SET source_artifact_id = :source WHERE id = :id",
            {"source": artifact["id"], "id": second["revisions"][0]["artifacts"][0]["id"]},
        ),
        ("UPDATE artifacts SET source_artifact_id = id WHERE id = :id", {"id": artifact["id"]}),
    ]
    assert revision["id"] != other_revision
    for sql, parameters in statements:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(sql), parameters)


def test_manifest_matches_checked_in_bytes():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert len(manifest["fixtures"]) == 4
    for fixture in manifest["fixtures"]:
        data = (FIXTURES / fixture["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == fixture["sha256"]
        assert len(data) == fixture["size_bytes"]


def test_migration_matches_orm_models(engine):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from traystack.models import Base

    with engine.connect() as connection:
        changes = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert changes == []


def test_api_documentation_assets_are_local(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert 'src="/api/docs-assets/swagger-ui-bundle.js"' in response.text
    assert client.get("/api/docs-assets/swagger-ui-bundle.js").status_code == 200
    assert client.get("/api/docs-assets/swagger-ui.css").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_png_and_escaped_metadata_roundtrip(client):
    from io import BytesIO

    from PIL import Image

    stream = BytesIO()
    Image.new("RGB", (16, 16), "white").save(stream, format="PNG")
    data = stream.getvalue()
    metadata = {"literal_escape": r"\u0000"}
    response = client.post(
        "/api/documents/upload",
        data={"title": "PNG", "metadata": json.dumps(metadata)},
        files={"file": ("image.png", data, "application/pdf")},
    )
    assert response.status_code == 201
    assert response.json()["metadata"] == metadata
    artifact = response.json()["revisions"][0]["artifacts"][0]
    assert artifact["mime_type"] == "image/png"
    assert client.get(f"/api/artifacts/{artifact['id']}/content").content == data

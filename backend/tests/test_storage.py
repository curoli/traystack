import hashlib
from io import BytesIO

import pytest

from traystack.services.storage import InvalidUpload, LocalStorage, UploadTooLarge


def test_roundtrip_deduplication_and_integrity(tmp_path):
    storage = LocalStorage(tmp_path)
    data = b"original bytes\r\n\x00\xff"
    blob = storage.put_stream(BytesIO(data), len(data))
    assert blob.sha256 == hashlib.sha256(data).hexdigest()
    assert storage.path_for(blob.storage_key).read_bytes() == data
    assert storage.put_stream(BytesIO(data), len(data)) == blob
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1
    storage.path_for(blob.storage_key).write_bytes(b"corrupt")
    with pytest.raises(OSError, match="integrity"):
        storage.put_stream(BytesIO(data), len(data))


def test_failed_upload_leaves_no_partial_file(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(UploadTooLarge):
        storage.put_stream(BytesIO(b"too long"), 4)
    with pytest.raises(InvalidUpload):
        storage.put_stream(BytesIO(b""), 4)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("key", ["../../etc/passwd", "/etc/passwd", "ab/cd/" + "0" * 64])
def test_opaque_keys_reject_traversal_and_malformed_hash(tmp_path, key):
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).path_for(key)


def test_storage_rejects_symlink_escape(tmp_path):
    root = tmp_path / "storage"
    storage = LocalStorage(root)
    (root / "ab").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        storage.path_for("ab/cd/" + "abcd" + "0" * 60)

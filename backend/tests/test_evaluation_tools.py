import json
import runpy
from collections import Counter
from pathlib import Path

from traystack.services.normalization import normalize_for_search

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    return runpy.run_path(str(ROOT / "scripts" / name))


def test_inventory_records_duplicate_bytes_without_changing_sources(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.txt").write_bytes(b"same content")
    (source / "two.txt").write_bytes(b"same content")
    (source / "binary.txt").write_bytes(b"\xff\x00")
    report = load_script("inventory_sources.py")["inventory"]([source])
    assert report["summary"]["files"] == 3
    assert report["summary"]["unique_byte_contents"] == 2
    assert report["summary"]["duplicate_files"] == 1
    assert all(not record["redistribution_verified"] for record in report["sources"])
    assert (
        next(row for row in report["sources"] if row["path"] == "binary.txt")["encoding"]
        == "unsupported"
    )
    assert (source / "one.txt").read_bytes() == b"same content"


def test_ground_truth_labels_offsets_and_family_splits_are_consistent():
    generated = load_script("generate_handwriting.py")["make_corpus"]()
    committed = json.loads((ROOT / "examples/synthetic-handwriting/ground_truth.json").read_text())
    assert generated == committed
    documents = generated["documents"]
    assert len(documents) == len({row["id"] for row in documents}) == 100
    assert Counter(row["case"] for row in documents) == {
        "exact": 20,
        "formatting": 20,
        "paraphrase": 20,
        "counterexample": 20,
        "unrelated": 20,
    }
    assert Counter(row["split"] for row in documents) == {"train": 70, "dev": 20, "test": 10}
    families = {}
    for row in documents:
        families.setdefault(row["group_id"], set()).add(row["split"])
        span = row["relevant_span"]
        clause = row["text"][span["start"] : span["end"]]
        assert clause and 0 <= span["start"] < span["end"] <= len(row["text"])
        assert (row["query"] in row["text"]) is row["expected_raw_literal"]
        assert (normalize_for_search(row["query"]) in normalize_for_search(row["text"])) is row[
            "expected_normalized_literal"
        ]
        if row["case"] == "counterexample":
            assert row["difference"] and not row["intended_semantic_match"]
    assert len(families) == 20 and all(len(splits) == 1 for splits in families.values())


def test_renderer_is_seeded_and_varies_actual_pixels():
    tools = load_script("generate_handwriting.py")
    fonts = json.loads((tools["FONTS"] / "sources.json").read_text())["fonts"]
    text = tools["make_corpus"]()["documents"][0]["text"]
    font = tools["FONTS"] / fonts[0]["file"]
    render = tools["render"]
    clear = render(text, font, "clear", 10)
    first = render(text, font, "irregular", 10)
    second = render(text, font, "irregular", 10)
    assert first.size == (1240, 1754)
    assert first.tobytes() == second.tobytes()
    assert first.tobytes() != clear.tobytes()
    assert len({row["file"] for row in fonts}) == 3


def test_manifest_import_cannot_escape_its_source_directory(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"images": [{"file": "../outside.jpg"}]}))
    import pytest

    with pytest.raises(ValueError, match="within its directory"):
        list(load_script("import_examples.py")["inputs"](manifest))


def test_cer_counts_insertions_deletions_and_substitutions():
    distance = load_script("evaluate_handwriting.py")["edit_distance"]
    assert distance("abc", "abc") == 0
    assert distance("abc", "axc") == 1
    assert distance("abc", "ac") == 1
    assert distance("abc", "abcd") == 1


def test_checked_in_image_samples_match_their_ground_truth_and_fonts():
    import hashlib

    from PIL import Image

    root = ROOT / "examples/synthetic-handwriting"
    manifest = json.loads((root / "samples/manifest.json").read_text())
    corpus = json.loads((root / "ground_truth.json").read_text())
    documents = {row["id"]: row for row in corpus["documents"]}
    assert len(manifest["images"]) == 3
    assert {row["difficulty"] for row in manifest["images"]} == {"clear", "irregular", "difficult"}
    assert len({row["font"] for row in manifest["images"]}) == 3
    for row in manifest["images"]:
        image = root / "samples" / row["file"]
        assert hashlib.sha256(image.read_bytes()).hexdigest() == row["sha256"]
        assert (
            hashlib.sha256((root / "fonts" / row["font"]).read_bytes()).hexdigest()
            == row["font_sha256"]
        )
        assert row["split"] == documents[row["document_id"]]["split"]
        assert row["requires_manual_review"] is True
        with Image.open(image) as opened:
            assert opened.size == (1240, 1754) and opened.format == "JPEG"

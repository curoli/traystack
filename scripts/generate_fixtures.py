"""Generate synthetic inputs. Requires the locked backend dependencies; no network."""

import hashlib
import json
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "examples" / "synthetic-contracts"
PHRASE = "The receiving party shall not disclose confidential information"


def pdf_bytes(title: str, body: str) -> bytes:
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_text(
            (50, 60), "SYNTHETIC DEMO CONTRACT - NOT A REAL AGREEMENT", fontsize=9
        )
        page.insert_text((50, 105), title, fontsize=18)
        page.insert_textbox(pymupdf.Rect(50, 150, 545, 700), body, fontsize=11)
        document.set_metadata(
            {"title": title, "author": "TrayStack synthetic fixtures"}
        )
        return document.tobytes(garbage=4, deflate=True, no_new_id=True)


def render(data: bytes) -> Image.Image:
    with pymupdf.open(stream=data, filetype="pdf") as document:
        pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    positive = pdf_bytes(
        "A - Confidentiality agreement",
        f"Parties: Example Company and Demo Partner.\n\n{PHRASE}.\n\nTerm: twelve months. Governing language: English.",
    )
    negative = pdf_bytes(
        "D - Delivery agreement",
        "Parties: Example Company and Demo Partner.\n\nThe supplier shall deliver the goods within thirty days.\nPayment is due within fourteen days of receipt.\n\nThis sample concerns deliveries and payment only.",
    )
    (ROOT / "A-confidentiality.pdf").write_bytes(positive)
    (ROOT / "D-delivery.pdf").write_bytes(negative)
    render(positive).save(ROOT / "P-printed-scan.jpg", quality=93, subsampling=0)
    difficult = render(negative).convert("L").resize((298, 421)).resize((1190, 1684))
    difficult = difficult.rotate(5, fillcolor=255).filter(ImageFilter.GaussianBlur(2.5))
    rng = random.Random(144)
    pixels = bytearray(difficult.tobytes())
    for index in range(len(pixels)):
        pixels[index] = max(0, min(255, pixels[index] + rng.randrange(-45, 46)))
    difficult = Image.frombytes("L", difficult.size, bytes(pixels))
    difficult.save(ROOT / "E-difficult-scan.jpg", quality=35)
    specs = [
        ("A", "A-confidentiality.pdf", False, True),
        ("D", "D-delivery.pdf", False, False),
        ("P", "P-printed-scan.jpg", False, True),
        ("E", "E-difficult-scan.jpg", True, False),
    ]
    manifest = {
        "target_phrase": PHRASE,
        "scope": "All files are synthetic. Search expectations apply after Milestones 2–3, not at upload time.",
        "generator_versions": {
            "pymupdf": pymupdf.VersionBind,
            "pillow": Image.__version__,
        },
        "fixtures": [],
    }
    for fixture_id, filename, manual, present in specs:
        data = (ROOT / filename).read_bytes()
        manifest["fixtures"].append(
            {
                "id": fixture_id,
                "file": filename,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "requires_manual_review": manual,
                "phrase_in_source": present,
                "milestone_1_expected": "not_processed; download bytes and sha256 match original",
                "normalized_contains_expected": "found"
                if present
                else "no positive match",
                "normalized_lacks_expected": "unverifiable"
                if manual
                else (
                    "excluded: phrase found"
                    if present
                    else "not_found_in_processed_text"
                ),
                "condition": "OCR must actually recover the phrase; otherwise surface real quality/failure status"
                if fixture_id == "P"
                else (
                    "Manual-review flag excludes negative eligibility regardless of OCR coverage"
                    if manual
                    else "Full extraction coverage and no known quality issue required for negative eligibility"
                ),
            }
        )
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()

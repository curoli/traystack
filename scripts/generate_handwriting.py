"""Reproducible font-based contract simulations, not samples of human handwriting."""

import argparse
import hashlib
import json
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "examples" / "synthetic-handwriting" / "fonts"
GENERATOR_VERSION = "handwriting-simulation-v1"
# Original short clauses for evaluation. No uploaded source content is copied.
# Query, paraphrase, deliberately different clause, reason for that difference.
TOPICS = [
    (
        "The receiving party shall not disclose confidential information.",
        "The recipient must keep the confidential material secret.",
        "The receiving party may disclose confidential information.",
        "negation",
    ),
    (
        "Payment is due within thirty days of receipt.",
        "The invoice must be paid no later than thirty days after it is received.",
        "Payment is due within ninety days of receipt.",
        "deadline",
    ),
    (
        "Liability is limited to 50,000 euros.",
        "The maximum liability under this agreement is fifty thousand euros.",
        "Liability is limited to 500,000 euros.",
        "amount",
    ),
    (
        "The supplier shall deliver the goods within fourteen days.",
        "Delivery of the goods by the supplier is required within two weeks.",
        "The supplier shall deliver the goods within forty days.",
        "deadline",
    ),
    (
        "Either party may terminate this agreement with thirty days notice.",
        "Each party can end the agreement by giving thirty days of notice.",
        "Only the supplier may terminate this agreement with thirty days notice.",
        "party_right",
    ),
    (
        "The contractor shall delete personal data after termination.",
        "When the contract ends, the contractor must erase personal information.",
        "The contractor shall retain personal data after termination.",
        "opposite_action",
    ),
    (
        "All intellectual property rights remain with the customer.",
        "The customer continues to own all intellectual property rights.",
        "All intellectual property rights transfer to the contractor.",
        "ownership",
    ),
    (
        "The supplier must obtain consent before appointing a subcontractor.",
        "A subcontractor can only be appointed after the supplier receives approval.",
        "The supplier may appoint a subcontractor without consent.",
        "consent",
    ),
    (
        "The agreement is governed by the laws of England.",
        "English law applies to this agreement.",
        "The agreement is governed by the laws of Germany.",
        "jurisdiction",
    ),
    (
        "The customer may audit the service once per year.",
        "An annual audit of the service may be carried out by the customer.",
        "The customer may not audit the service.",
        "negation",
    ),
    (
        "The supplier shall notify the customer of a breach within 24 hours.",
        "The customer must be told about a breach by the supplier within one day.",
        "The supplier shall notify the customer of a breach within 72 hours.",
        "deadline",
    ),
    (
        "Insurance coverage shall be at least 1,000,000 euros.",
        "The insured amount must be one million euros or more.",
        "Insurance coverage shall be at least 100,000 euros.",
        "amount",
    ),
    (
        "The warranty period is twelve months from delivery.",
        "The delivered goods carry a warranty lasting twelve months.",
        "The warranty period is two months from delivery.",
        "duration",
    ),
    (
        "Expenses require prior written approval.",
        "Written permission must be obtained before incurring expenses.",
        "Expenses do not require prior written approval.",
        "negation",
    ),
    (
        "Service credits are capped at ten percent of the monthly fee.",
        "Credits for service failures cannot exceed a tenth of the monthly charge.",
        "Service credits are capped at fifty percent of the monthly fee.",
        "amount",
    ),
    (
        "All disputes shall be resolved by arbitration.",
        "Disagreements under this contract must be settled through arbitration.",
        "All disputes shall be resolved by the ordinary courts.",
        "procedure",
    ),
    (
        "The customer owns all equipment supplied under this agreement.",
        "Ownership of all equipment provided under the agreement belongs to the customer.",
        "The supplier owns all equipment supplied under this agreement.",
        "ownership",
    ),
    (
        "Assignment of this agreement requires the other party's consent.",
        "A party must obtain the other's permission before transferring the agreement.",
        "Assignment of this agreement does not require the other party's consent.",
        "negation",
    ),
    (
        "The contractor shall provide support during business hours.",
        "Support from the contractor is available within normal working hours.",
        "The contractor shall provide support only outside business hours.",
        "time_scope",
    ),
    (
        "The supplier shall maintain backups for thirty days.",
        "Backup copies must be kept by the supplier for thirty days.",
        "The supplier shall maintain backups for three days.",
        "duration",
    ),
]


def make_corpus():
    documents = []
    for index, (query, paraphrase, different, reason) in enumerate(TOPICS):
        family = f"clause-{index + 1:02d}"
        split = "train" if index < 14 else ("dev" if index < 18 else "test")
        cases = {
            "exact": query,
            "formatting": "\n".join(textwrap.wrap(query.swapcase(), width=38)),
            "paraphrase": paraphrase,
            "counterexample": different,
            "unrelated": "Routine correspondence is sent to the registered office address.",
        }
        for case, clause in cases.items():
            doc_id = f"{family}-{case}"
            prefix = (
                "SYNTHETIC CONTRACT - FONT SIMULATION\n"
                f"Reference: {doc_id}\n\n"
                f"Parties: Example Company {index + 1:02d} and Demo Partner {index + 1:02d}.\n\n"
            )
            suffix = (
                "\n\nThis fictional short agreement is for software evaluation only."
            )
            documents.append(
                {
                    "id": doc_id,
                    "group_id": family,
                    "split": split,
                    "case": case,
                    "query": query,
                    "text": prefix + clause + suffix,
                    "relevant_span": {
                        "start": len(prefix),
                        "end": len(prefix) + len(clause),
                    },
                    "expected_raw_literal": case == "exact",
                    "expected_normalized_literal": case in {"exact", "formatting"},
                    "intended_semantic_match": case
                    in {"exact", "formatting", "paraphrase"},
                    "semantic_label_basis": "author-written test intent, not a legal equivalence ruling",
                    "difference": reason if case == "counterexample" else None,
                    "source": "original TrayStack evaluation clauses; no source corpus text copied",
                    "font_index": index % 3,
                }
            )
    return {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "documents": documents,
    }


def wrap_pixels(text, draw, font, max_width):
    result = []
    for line in text.split("\n"):
        current = ""
        for word in line.split():
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=font) > max_width:
                result.append(current)
                current = word
            else:
                current = candidate
        result.append(current)
    return result


def render(text, font_path, difficulty, seed):
    rng = random.Random(seed)
    image = Image.new("L", (1240, 1754), 250)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(font_path), 42)
    lines = wrap_pixels(text, draw, font, 1030)
    y = 85
    for line in lines:
        if y + 55 > image.height - 80:
            raise ValueError("Text would be clipped; increase canvas before generating")
        jitter = rng.randint(-8, 8) if difficulty != "clear" else 0
        draw.text((90 + jitter, y), line, font=font, fill=rng.randint(22, 55))
        y += 53 + (rng.randint(-3, 5) if difficulty != "clear" else 0)
    if difficulty != "clear":
        angle = 1.2 if difficulty == "irregular" else -3.0
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=250)
        if difficulty == "difficult":
            image = image.resize((620, 877)).resize(image.size)
            image = image.filter(ImageFilter.GaussianBlur(0.8))
        # Vary paper brightness and scanner noise without creating false ground truth.
        pixels = bytearray(image.tobytes())
        noise = 5 if difficulty == "irregular" else 15
        for i, value in enumerate(pixels):
            pixels[i] = min(255, max(0, value + rng.randint(-noise, noise)))
        image = Image.frombytes("L", image.size, bytes(pixels))
    return image


def generate(output, limit=100):
    output.mkdir(parents=True, exist_ok=True)
    corpus = make_corpus()
    documents = corpus["documents"][:limit]
    font_sources = json.loads((FONTS / "sources.json").read_text())
    font_records = font_sources["fonts"]
    records = []
    for number, document in enumerate(documents, 1):
        record_font = font_records[document["font_index"]]
        font_path = FONTS / record_font["file"]
        for difficulty in ["clear", "irregular", "difficult"]:
            seed = int.from_bytes(
                hashlib.sha256(f"{document['id']}:{difficulty}".encode()).digest()[:8],
                "big",
            )
            image = render(document["text"], font_path, difficulty, seed)
            filename = f"{document['id']}-{difficulty}.jpg"
            image.save(output / filename, quality=90 if difficulty == "clear" else 65)
            records.append(
                {
                    "id": f"{document['id']}-{difficulty}",
                    "document_id": document["id"],
                    "group_id": document["group_id"],
                    "split": document["split"],
                    "file": filename,
                    "sha256": hashlib.sha256(
                        (output / filename).read_bytes()
                    ).hexdigest(),
                    "difficulty": difficulty,
                    "seed": seed,
                    "font": record_font["file"],
                    "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
                    "requires_manual_review": True,
                }
            )
        if number % 10 == 0:
            print(f"Rendered {number} contracts ({number * 3} images)", flush=True)
    from PIL import __version__ as pillow_version
    from PIL import features

    manifest = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "pillow_version": pillow_version,
        "freetype_version": features.version("freetype2"),
        "jpeg_version": features.version("jpg"),
        "kind": "font-based simulation, not real human handwriting",
        "ground_truth_file": "ground_truth.json",
        "images": records,
    }
    corpus["documents"] = documents
    (output / "ground_truth.json").write_text(json.dumps(corpus, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data" / "synthetic-handwriting"
    )
    parser.add_argument(
        "--limit", type=int, choices=range(1, 101), default=100, metavar="1..100"
    )
    parser.add_argument("--ground-truth-only", action="store_true")
    args = parser.parse_args()
    if args.ground_truth_only:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "ground_truth.json").write_text(
            json.dumps(make_corpus(), indent=2) + "\n"
        )
        return
    manifest = generate(args.output, args.limit)
    print(
        f"Generated {len(manifest['images'])} JPEGs with ground truth in {args.output}"
    )


if __name__ == "__main__":
    main()

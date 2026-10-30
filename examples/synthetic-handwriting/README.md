# Synthetic handwriting-style evaluation corpus

These are **font-based simulations**, not samples of real human handwriting or
historical contracts. There are 100 original short English contract texts and
300 generated JPEGs: three degradation levels for each text. No uploaded contract
text, names or personal information were copied into these synthetic clauses.

The generator uses bundled, unmodified Caveat, Kalam and Patrick Hand fonts.
Their upstream commit and URLs are recorded in [font sources](fonts/sources.json),
and each font directory contains its original SIL Open Font License text.
The generator runs offline with the locked Pillow dependency; images record font
hash, random seed and Pillow/FreeType/JPEG versions.

## Contents

- [ground_truth.json](ground_truth.json): all 100 source texts, target queries,
  logical clause offsets, intended semantic labels and literal expectations.
- [samples](samples/manifest.json): three checked-in JPEGs, one per font and
  degradation level, ready to upload or import. These are examples, not a
  representative evaluation sample.
- [evaluation-train45.json](evaluation-train45.json): actual local OCR outputs and
  metrics for the first 45 images in the training split. No semantic model was run.
- Fonts and their licenses are bundled; the other 297 JPEGs are reproduced locally
  rather than adding approximately 42 MB of generated image content to Git.

## Generate all 300 images

From the repository root after installing the locked backend dependencies:

```sh
.venv/bin/python scripts/generate_handwriting.py
```

Output: `data/synthetic-handwriting/`, containing `manifest.json`,
`ground_truth.json` and 300 JPEGs (1240 × 1754 pixels).
Generation takes a few minutes on a typical development machine.
`data/` is ignored by Git. No API calls or model downloads occur during generation.

For a small rehearsal, use a separate output directory:

```sh
.venv/bin/python scripts/generate_handwriting.py --limit 5 --output data/handwriting-small
```

`--limit` selects source texts; each produces three images. Existing files are
not removed when regenerating a smaller subset. Use the generated manifest as
its authoritative file list, rather than importing every JPEG in that directory.
Identical library versions, bundled fonts and seeds reproduce the image bytes;
different rendering/codec versions may change them. The checked-in ground truth
can be regenerated independently with:

```sh
.venv/bin/python scripts/generate_handwriting.py --ground-truth-only --output examples/synthetic-handwriting
```

## Ground truth and splits

Twenty clause families each have five cases: exact, changed case/line wrapping,
paraphrase, a deliberately different clause, and unrelated text. Counterexamples
change negation, amount, deadline, ownership, consent or another material detail.
`intended_semantic_match` is an author-written evaluation label, **not a legal
ruling**. The labeled span uses zero-based Unicode code points, end exclusive,
in the original synthetic text. OCR naturally has different offsets.

All five cases and all image degradations of one family stay in the same split:

| Split | Clause families | Source texts | Images |
|---|---:|---:|---:|
| Train | 14 | 70 | 210 |
| Dev | 4 | 20 | 60 |
| Test | 2 | 10 | 30 |

This avoids placing different renderings or paraphrases of the same family on
both sides of an evaluation. Generic headers are still shared; this small,
constructed corpus is not evidence of generalization to real contracts.
Use train for development, dev for threshold decisions, and keep test untouched
until the search implementation is fixed. The initial OCR measurement uses train
only; no thresholds have been calibrated and no test-split OCR was evaluated.

All generated images must retain `requires_manual_review: true`, including the
clear versions. A missing OCR match must stay unverifiable in the app. The
sidecar's original transcription is for evaluation only: it is never substituted
for extracted image text or sent to the search index by the importer.

## Import and measure

With the app and worker running:

```sh
.venv/bin/python scripts/import_examples.py examples/synthetic-handwriting/samples/manifest.json --limit 3 --process
.venv/bin/python scripts/import_examples.py data/synthetic-handwriting/manifest.json --limit 300 --process
```

The second command processes every image through actual OCR and can take several
minutes. The importer retains the review flag from the manifest and checks image
hashes before upload. It does not import ground-truth queries, labels or text.
See [data and evaluation](../../docs/data-evaluation.md) for receipt/retry behavior.

Reproduce the measured OCR baseline:

```sh
OMP_THREAD_LIMIT=1 .venv/bin/python scripts/evaluate_handwriting.py data/synthetic-handwriting/manifest.json --split train --limit 45 --output data/handwriting-evaluation-train45.json
```

This calls the production extraction service on image bytes, independently of
the application database. It records actual OCR text, engine versions, source
hashes and parameters. The character error rate uses Levenshtein distance after
the existing whitespace/case/Unicode normalization; it is not a raw-layout score.
Literal precision/recall compare query presence after real OCR with source labels.
A missed positive counts as a false negative even though the app correctly
classifies it as unverifiable for review. Paraphrases are negative for literal
matching even when their intended semantic label is positive.

The initial measured results and their limits are in
[the evaluation report](../../docs/data-evaluation.md#measured-ocr-baseline).

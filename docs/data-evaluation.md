# Data import and evaluation foundation

Implemented after the English UI. This increment adds real TXT/HTML ingestion,
a local source inventory, a repeatable synthetic image corpus, import tooling and
an OCR baseline. The subsequent [textual similarity workflow](textual-search.md)
now evaluates positive candidates against this data. Semantic thresholds,
embeddings, per-occurrence review states and revision-management UI remain later work.

## Local source inventory

The user-provided directories contain the following bytes as inventoried on
30 October 2026:

| Directory | Files | Formats |
|---|---:|---|
| `examples/contracts/` | 152 | UTF-8 TXT |
| `examples/contract-nli/` | 607 | 375 PDF, 113 HTM, 119 UTF-8 TXT |
| Combined | 759 | 756 unique byte contents; three duplicate copies |

The combined byte size is 127,133,068. All 384 TXT/HTM files decode as UTF-8.
Directory names do not verify their original dataset source, annotation coverage
or redistribution license. No accompanying source/license files were found.
The original collections and the file-level inventory stay local and are ignored
by Git; this PR contains neither their text nor copies of those documents.
The synthetic evaluation clauses are independently authored rather than copies.

Recreate a file-level inventory with relative names, byte sizes, SHA-256, encoding
and explicit unverified provenance:

```sh
.venv/bin/python scripts/inventory_sources.py examples/contracts examples/contract-nli --output data/source-inventory.json
```

This is read-only with respect to source files. Symlink files are skipped.
The local report can later be enriched with verified origin/license information.
Duplicate hashes are useful for import planning; they do not prove that two
separate logical contracts are the same legal document.

## Native TXT and HTML ingestion

The existing upload API and English UI now accept `.txt`, `.htm` and `.html`,
alongside PDF/JPEG/PNG. They use the same size limit, immutable artifact storage,
processing queue, canonical text publication and original-byte downloads.

- TXT/HTML must be non-empty UTF-8 (UTF-8 BOM accepted), without binary control
  characters. There is no guessed legacy encoding or silent replacement decoding.
- TXT is read as source text, including literal markup if present in a TXT file.
- HTML is read with Python's non-executing `HTMLParser`. Script/style/head/template
  content is omitted. No external images, frames, CSS or scripts are requested or run.
  Inline markup keeps words intact; common block boundaries produce line breaks.
- HTML is **always marked for review**. Images are not OCR'd, CSS visibility and
  layout order are not reconstructed, and hidden text may be included. Its absence
  results remain unverifiable. Image-only HTML produces unavailable text.
- Both formats have one **logical page**, not a physical page reference. The page
  viewer says so explicitly; page 1 means the text document, not a claimed PDF page.
- HTML is never rendered into the app as HTML. Text previews use escaped text;
  original downloads remain attachments with `nosniff`.
- New runs record `text_documents: utf8-html-text-v1` in engine provenance.
  Extraction quality still applies separately from technical completion.

## Controlled local import

After `docker compose up --build`, from the repository root:

```sh
# Inspect the first 20 selected files without changing the app.
.venv/bin/python scripts/import_examples.py examples/contracts --limit 20 --dry-run

# Upload and really process a bounded batch.
.venv/bin/python scripts/import_examples.py examples/contracts --limit 20 --process --manual-review

# Import the generated image manifest, preserving review and split metadata.
.venv/bin/python scripts/import_examples.py data/synthetic-handwriting/manifest.json --limit 15 --process
```

A source may be one supported file, a directory (recursive, sorted), or a generated
image manifest. Use the manifest for synthetic images: it carries the review flag
and expected file hashes. Paths in image manifests cannot escape the manifest's
directory. Ground truth is not used as source text or uploaded as metadata.

The default limit is 20; no automatic full-corpus import occurs. Uploads create
separate documents with a first revision; this is not a revision/representation
management API. Original bytes are preserved, and import source/hash plus synthetic
group/split/difficulty are attached as metadata. Review flags are carried through.
Processing waits for real jobs, reports actual failures and has a bounded wait.

`data/import-receipts.json` records a versioned key containing endpoint + source
MIME type + byte hash + review intent → document ID. The source type uses the
server's extension mapping: `.htm`/`.html` share a type, as do `.jpg`/`.jpeg`;
TXT and HTML never reuse one another even when their bytes are identical.
A repeated single-process import checks whether that document still exists and
reuses it. A pending job is awaited; a completed job is retained. A failed run can
be processed again. Receipts are saved immediately after upload, so processing
failure can be resumed. Different review intent creates a separate document rather
than reusing a less restrictive import. Equal bytes at different paths are reused
by this convenience tool only when their processing type and review intent also
match; application-level document identity remains separate.

Legacy keys without a type are retained in the receipt file but are not reused.
The first import with the new key therefore creates a new document, even for a
previously imported file. This avoids guessing a processing type from unsafe old
receipts. Existing app documents are not rewritten: reimport any HTML previously
misidentified as TXT to obtain its proper text extraction and quality warnings.
The receipt fix was verified with 122 passing backend tests, including real
API/worker execution in both TXT→HTML and HTML→TXT import orders, repeat reuse,
legacy receipts and uppercase `.HTM` alias reuse. The frontend was unchanged;
the 13 browser scenarios documented below were not rerun for this receipt fix.

Receipts are local to this tool and are not a distributed idempotency protocol:
concurrent imports, a lost receipt or interruption between server upload and
receipt save can create another document. Do not run concurrent importers with
the same receipt file. Pass `--receipts` for a separate import context and
`--base-url` for another local stack. The API is unauthenticated in this prototype.

## Synthetic image dataset

See [corpus instructions](../examples/synthetic-handwriting/README.md) for the
300 JPEGs, bundled fonts and licenses, ground truth and split rules. Three samples
and the full 100-text ground truth are committed. All 300 JPEGs were generated
locally under `data/synthetic-handwriting/` (41,678,331 JPEG bytes); generated images
and application imports are not required to be checked into Git.

Font-based rendering is deliberately labeled as simulation. Three font families,
line jitter, rotation, resampling, blur, scanner noise and JPEG compression exercise
recognition errors. These are short, single-page English examples, not historical
handwriting, signatures, multi-page contracts or a language-diverse legal benchmark.

## Measured OCR baseline

Actual run on 30 October 2026, recorded in
[evaluation-train45.json](../examples/synthetic-handwriting/evaluation-train45.json).
The first 45 training images cover three clause families, all three fonts, all five
cases and all three degradation levels. This is a selected development baseline,
not a random or held-out accuracy estimate. Dev/test were not used.

| Metric | Actual observation |
|---|---:|
| Evaluated images | 45 of 300 |
| Source images containing the normalized literal query | 18 |
| Correctly recovered positive passages | 12 |
| Missed literal positives | 6 |
| False positive literal matches | 0 among 27 source negatives |
| Literal precision | 12/12 = 100% in this sample |
| Literal recall | 12/18 = 66.7% in this sample |
| Aggregate normalized character error rate | about 0.98% |
| App-equivalent warned positives / unverifiable | 12 / 33 |

All images carry mandatory manual review: no absence result is considered
trustworthy. The 33 unverifiable outputs include both unread positive passages and
source negatives, so they must not be reported as 33 OCR errors. Even a low
aggregate character error rate can break an otherwise long literal phrase.
Scores depend on font, layout and engine version; difficult is a generation label,
not a guarantee of monotonically worse recognition for every image.

The report includes engine versions, parameters, image hashes, manifest and
transcription hashes, and actual recognized text. The run uses local Tesseract
rather than the Compose container; its recorded version is authoritative for
these measurements. Embeddings, semantic accuracy and threshold recommendations
have not been measured. The authored semantic labels prepare those future checks.

## Verification

The implementation is checked with PostgreSQL integration tests for upload →
processing → exact/normalized search → original download, plus malformed UTF-8,
binary/empty files, logical page provenance, HTML script exclusion and image-only
HTML remaining unverifiable. Tool tests check inventory duplicates, ground-truth
spans/labels, split separation, seeded rendering, sample hashes and path traversal.
Browser tests exercise both new formats through the real worker and verify that
HTML scripts and external image URLs are not executed/requested.

The live importer was also run on one supplied TXT, one HTM and one PDF, then
repeated to confirm receipt reuse; source bytes were not changed. Three synthetic
image samples were uploaded and processed through the app with mandatory review.
Final validation on 30 October 2026: **120 backend tests** against the isolated
PostgreSQL database and **13 Playwright/Chrome scenarios** passed. TypeScript/Vite,
Ruff checks/formatting, Prettier, local Markdown file links, all 300 image hashes,
report source hashes and `git diff --check` passed. Alembic's model/schema check
reported no differences. The known Starlette/HTTPX TestClient deprecation warning
remains; no runtime dependency or migration was added.

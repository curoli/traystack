# Using TrayStack

This guide explains the current local prototype from a user's perspective. Labels
match the English interface. Documents and queries can be in English, German or
other languages. Updated: 1 November 2026.

## Contents

1. [Start and stop the app](#1-start-and-stop-the-app)
2. [Components and terminology](#2-components-and-terminology)
3. [Upload a document](#3-upload-a-document)
4. [Process a document and interpret its status](#4-process-a-document-and-interpret-its-status)
5. [Differences between file types](#5-differences-between-file-types)
6. [Find documents containing a phrase](#6-find-documents-containing-a-phrase)
7. [Identify documents without an active match](#7-identify-documents-without-an-active-match)
8. [Review passages and navigate](#8-review-passages-and-navigate)
9. [Reopen searches and export results](#9-reopen-searches-and-export-results)
10. [Troubleshooting and limitations](#10-troubleshooting-and-limitations)

## 1. Start and stop the app

### Requirements and startup

You need the checked-out repository, Docker with Compose v2, and access to the
Docker daemon. Python, Node and OCR tools do not need separate host installations
for normal Docker operation.

The first build downloads container images, dependencies and the pinned local
embedding model/tokenizer (about 135 MB). Once built, the app processes documents
and calculates embeddings locally without cloud services or API keys.

From the repository directory:

```sh
cd /home/oliver/git/traystack
docker compose up -d --build --wait
```

Adjust the directory on another machine. Open:

| Address | Purpose |
| --- | --- |
| <http://localhost:8080> | Application |
| <http://localhost:8080/docs> | Interactive REST API documentation |
| <http://localhost:8000/api/health> | API, database and storage readiness |

The first build takes longer. Inspect services and recent errors with:

```sh
docker compose ps -a
docker compose logs --tail=100 api worker migrate
```

`migrate` applies database migrations and normally exits with code 0; it does not
need to remain running. Subsequent starts without code changes normally need only
`docker compose up -d --wait`.

### Configuration and OCR language

Defaults work without `.env`. To customize them, copy `.env.example` to `.env` and
edit the relevant values. Multilingual PaddleOCR is the default:

```dotenv
OCR_BACKEND=paddleocr
```

PP-OCRv6 small runs locally through RapidOCR/ONNX Runtime and includes English and
German. Model files are included during the image build. For the previous engine,
set `OCR_BACKEND=tesseract`; only that engine uses `OCR_LANGUAGES=eng+deu`.
Run `docker compose up -d --wait` to apply changed container settings. Existing text
is not recalculated automatically: use **Reprocess** for affected documents.
OCR language is independent of the English interface language.

`WEB_PORT` and `API_PORT` change local ports. Open the corresponding web port if
you change `WEB_PORT`.

### Stop without deleting data

```sh
docker compose down
```

This stops services while retaining documents, saved searches and decisions in
Docker volumes. They return on the next start. **`docker compose down -v` deletes
the associated data volumes.** Do not use it if you need to retain stored data.
A full backup needs both the database and file storage; a result export is not a
replacement for that backup.

## 2. Components and terminology

| Component | Responsibility |
| --- | --- |
| React/TypeScript interface | Uploads, document details, search, review and export |
| Nginx web server | Serves the interface and forwards API calls to FastAPI |
| Python/FastAPI API | Validates input, stores metadata, queues jobs, searches, and saves decisions/search runs |
| Worker | Claims queued jobs, extracts text or performs OCR, and publishes results |
| PostgreSQL | Documents/revisions, jobs, search text, quality metadata, saved runs and decisions |
| File storage | Unchanged originals and derived files in a Docker volume |
| Migration service | Updates the database schema at startup |
| Local embedding model | Optionally compares the query with already retrieved textual passages; not a separate Compose service |

Upload and processing controls live under **Manage documents**, collapsed by
default so search users can work without processing details.

The worker uses PyMuPDF for PDFs and PaddleOCR for image OCR (Tesseract remains a legacy option). The API uses character
comparison for textual similarity and optionally the local model for semantic
comparison. The worker runs independently of the browser: accepted jobs can
continue after closing the browser while services remain running. Uploading alone
does not start processing in the interface.

The domain distinguishes:

- **Document:** a logical contract with a title.
- **Revision:** a particular content version. A changed contract is a new revision.
- **Artifact/representation:** a file for a revision, such as the original or derived
  JSON/Markdown. Another scan of the same content is not a new contract revision.
- **Processing run/job:** an attempt to read a particular source. Repeated OCR
  produces another run and new derivatives.

Normal upload creates a document, its first revision and an original artifact.
Another **Add a contract** upload creates another document; files are not
implicitly grouped into revisions. Convenient creation of additional revisions
and representations in the interface is not yet delivered, although the domain
model distinguishes them.

## 3. Upload a document

1. Expand **Manage documents**, then open **Add a contract**.
2. Enter a useful **Title**, for example `Supply agreement – Oldname Ltd – 2022`.
3. Select an **Original file**: PDF, JPEG, PNG, UTF-8 TXT or HTML.
4. Optionally assign **Category (optional)**. Categories can later be edited under
   Manage documents with **Category** and **Save category**, without reprocessing.
5. Enable **Manual review required** for handwriting or difficult scans.
6. Choose **Save document**.

The default file limit is 25 MiB. Files are validated; renamed, damaged or
unsupported files may be rejected. DOCX, email files and ZIP archives are not
supported uploads.

### What happens immediately after upload?

The API preserves the original bytes, calculates SHA-256 and creates the document,
first revision and original artifact. The entry appears in the library and its
details open. Details include file type, size, identifiers and checksum.
**Download original** returns the same original bytes.

Initially the document is **Not processed** / **Not processed yet**. It is stored,
but has no processed search text. It must not be treated as confirmed to lack a
phrase simply because extraction has not happened.

**Manual review required** is a persistent source flag. Successful OCR does not
clear it. Choosing **Keep** for a passage does not approve extraction quality.

## 4. Process a document and interpret its status

1. Expand **Manage documents** and click the document in the library.
2. Select its original under **Processing source**. A single original is normally
   selected automatically.
3. Set **Manual review required** if appropriate.
4. Choose **Start processing**.
5. Watch the automatically refreshed status.

| Display | Meaning |
| --- | --- |
| **Queued for processing** | Waiting for the worker |
| **Processing** | Worker is reading the source |
| **Processed** | Run completed; coverage and quality still need inspection |
| **Processing failed** | Run failed; inspect its error details |

The worker extracts text or performs OCR, creates page text and full search text,
and builds a normalized search representation. Each run records source identity,
method, versions, page coverage and quality warnings. Derived artifacts include
structured extraction JSON and extracted Markdown. The original is not rewritten.

Use **View page text** and its page selector to inspect extracted content.
JSON/Markdown artifacts offer **Text preview** when small enough and **Download
file**. These are text views, not faithful PDF/image renderings. Use **Download
original** to compare with the actual contract image.

### Keep three kinds of status separate

| Level | Examples | Question answered |
| --- | --- | --- |
| Job | **Processed**, **Processing failed** | Did the run finish? |
| Coverage | **Fully processed**, **Partially processed**, **Text unavailable** | Were all pages processed, or is text missing? |
| Quality | **No known quality issue**, **Manual review required**, **Quality not assessed** | Are there known problems or required checks? |

**Processed** does not mean error-free recognition. **No known quality issue** is
not a guarantee of complete content accuracy. OCR word scores are engine signals,
not probabilities of legal correctness. Empty or unreadable pages are flagged
conservatively.

**Reprocess** creates another run and new derivatives. Earlier artifacts remain
available. Publishing new results replaces the revision's selected search text;
a failed run retains any previously selected text for inspection in Manage
documents, but the document stays outside new ready-only searches until a suitable
current result is published.
**Retry as a new run** retries a failed job. Repeating does not automatically fix
bad scans or damaged files. Saved searches retain their historical matches and
source text even after successful reprocessing.

## 5. Differences between file types

| Input | Processing | What to inspect |
| --- | --- | --- |
| Digital PDF page with usable embedded text and no image content | Read embedded PDF text | Reading order, special characters and unusual layouts |
| Scanned PDF, or page containing images or too little embedded text | Render the entire page and run the configured OCR engine | Mixed text/image pages also use this conservative OCR path; recognition errors remain possible |
| JPEG/PNG | OCR; one image is one page | Resolution, rotation, blur and handwriting |
| UTF-8 TXT | Read text without OCR | Logical text page rather than a printed page reference |
| UTF-8 HTML | Extract text without executing scripts or fetching external content | Images/layout are not fully examined; HTML always requires review |

PDF processing is decided per page, so methods can differ within one document.
JPEG does not imply handwriting: a photograph of printed text also uses OCR.

Handwriting is attempted with the same OCR engine. Reliable recognition of real
handwritten contracts is not guaranteed. Flag these files and inspect originals.
The repository's synthetic handwriting examples are test material, not evidence
of general handwriting recognition quality.

Defaults include 100 pages per run and 30 seconds per OCR call. Encrypted PDFs
and unsupported image variants may fail. Missing pages or processing errors are
not replaced with invented text. Run records expose the actual processing method.

## 6. Find documents containing a phrase

There is one search interface. Enter the company name or phrase under **Text
passage**, choose a comparison mode and select **Document category** (All,
Uncategorized or one category). Set **Minimum textual match** to 100 for literal
wording; Normalized ignores case/whitespace differences while preserving numbers,
negation, punctuation and hyphens. Original retains case and whitespace. This is not
regex, stemming or legal-meaning search.

Semantic scoring is always enabled for new UI searches. Set **Minimum semantic
match** (initially 50) to 0 to retain all textual candidates with their scores, or choose a higher
minimum to filter them further. Semantic 100 retains identical comparison text.
Choose **Find passages**. The latest revision's ready text is searched within the
selected category; the library page does not limit the scope.

By default, passages at 100 textual and 100 semantic are automatically confirmed.
They are counted but hidden. Enable **Show automatically confirmed passages for
review** to inspect or change them. Use **Auto-confirm strong matches** to disable
this behavior or set separate auto-confirmation thresholds. These differ from the
retrieval thresholds: retrieval chooses candidates, auto-confirm chooses which
candidates can skip manual review. Manual decisions always win.

## 7. Identify documents without an active match

Below the passage list, expand these document groups:

1. **Documents with at least one confirmed match**.
2. **Documents with no confirmed match but at least one unreviewed match**.
3. **Documents with no confirmed or unreviewed match**.

Each initially shows only a document count. The third group includes documents
with no candidate passing the search thresholds and documents whose candidates
were all dismissed. It is not proof that a legal clause is missing; similar wording
may fail the thresholds, OCR may contain errors, or a human may have dismissed
actual wording. Use textual 100 when testing precise wording, inspect original
files and account for explicit decisions before drawing conclusions.

Groups cover all ready documents in the captured category/scope, including those
without candidates. Pending/problematic sources remain under Manage documents,
not in any result group. Confirmation takes precedence when a document has both
confirmed and pending passages. The literal contains/absence API is still available
to integrations, but its separate interface has been removed.

## 8. Review passages and navigate

The compact list and selected detail pane show matched text, context, textual and
semantic scores, and highlighted differences. Scores are not probabilities of
correct meaning. Changed names, amounts, deadlines or negation can matter despite
high similarity. Model comparison uses the passage, not displayed surrounding text.
Textual zero is disallowed; query-specific warnings and budgets limit broad scans.
An aborted search never presents a successful partial list.

Each passage has exactly one selected state:

| Button | Meaning |
| --- | --- |
| **Match Confirmed** | Keep this passage as a match for the query |
| **Match Dismissed** | Reject this passage as a match |
| **Unreviewed** | Initial pending state, or an explicit reset |

State choices save without moving away. Automatically confirmed matches can also
be dismissed or reset; explicit choices are never silently replaced by the
algorithm. Old deferred decisions appear as Unreviewed. A failed save leaves the
previous state and selection intact; refresh after a version conflict.

**Previous unreviewed / Previous / Next / Next unreviewed** change passages
without modifying states, including passages within the same document. Pending
navigation skips confirmed/dismissed passages and stops at boundaries. You can
also select any visible passage directly from the list. Up/Down and Home/End select list entries; Tab and native
Enter/Space activate buttons. Search parameters can be collapsed while reviewing.

The three document groups update after confirmed saves. Hidden automatic matches
still contribute to counts. Expand a group to select a document or download its
original. A document with no candidates shows its own empty detail view, not
another document's passage. **View source text** opens the preserved extraction;
use **Download original** for the actual page image.

### View original documents in the browser

Choose **View original ↗** beside a passage, in an expanded document group, in the
saved source reader, or on an original artifact under Manage documents. It opens
that original in a separate browser tab and keeps the search/review selection in
place. PDFs use the browser's PDF viewer; JPEG/PNG display as images, TXT as text,
and HTML as a sandboxed page. This shows the uploaded file rather than OCR text.

HTML scripts, forms and external resources are blocked in this view. Inline styles
and embedded data images can render, but pages relying on remote assets can look
different. **Download original** remains available and saves the unchanged bytes,
including any original HTML markup/resources references. Browser preferences can
override inline viewing, especially a setting that always downloads PDFs.

## 9. Reopen searches and export results

Successful searches automatically save complete candidates, scores, category,
document scope, sources and auto-confirmation policy. Use **Saved searches** or a
bookmark URL containing `search_run` to reopen without retrieval or model calls.
Selecting a saved search collapses the saved-search list.
**Save name** changes only the label. **Run again** creates a separate linked run
with the original criteria against the current collection. To change criteria,
edit parameters and choose Find passages.

Category edits, uploads and reprocessing do not rewrite an old snapshot. Explicit
passage decisions are saved for that search and version-protected; their capture-time
state is retained separately. Every new search (including Run again) starts a fresh
review, apart from its own auto-confirmations. Reopening retains its decisions.
Older saved searches retain their legacy shared annotations; the interface identifies
these as historical. Reading auto-confirmed results creates
no manual decision records. Use **Refresh reviews** to load external changes.

For exports, expand **Export results**, choose **Export review status** (all,
confirmed, dismissed or unreviewed passages) and download CSV or JSON. This filters
passages, not documents, and is independent of hidden auto-confirmations in the
screen list. Export includes every selected occurrence, not just the active one.

CSV includes summary/passage rows, categories, policy and automatic/manual
provenance. Formula-like strings receive an apostrophe for spreadsheet safety.
JSON preserves exact text, differences, the full captured scope and document
outcomes. Search/export times are separate; current decisions come from one export
snapshot. Original files are not embedded. Historical captures retain original
source evidence; legacy deferred decisions are treated as pending in UI exports.

## 10. Troubleshooting and limitations

| Symptom | Check or action |
| --- | --- |
| Interface unavailable | Inspect `docker compose ps -a`, logs and `WEB_PORT` |
| 502 after replacing the API container | Run `docker compose restart frontend` to refresh Nginx's internal API address |
| Upload saved but no search text | Start processing; storage alone does not extract text |
| Job remains queued | Check the worker and `docker compose logs --tail=100 worker` |
| Incorrectly recognized words | Compare page text with the original; consider a better scan, appropriate OCR language and reprocessing |
| No visible passages | Check the automatic confirmation count and Show automatically confirmed passages, then wording/thresholds/category |
| Fewer negative results than expected | Inspect Manage documents for preparation issues; excluded documents are not confirmed negatives |
| Broad search stopped | Raise the threshold, refine wording or choose a narrower category; no successful partial list is returned |
| Saved run shows old text after OCR | Expected: use Run again for current results |
| Review changed elsewhere | Refresh reviews and inspect the current decision |

A hard worker crash can leave a job running. Recovery requires stopping all workers
first; follow [worker recovery](../README.md#recover-a-job-after-a-worker-crash).
Do not simply start competing workers to take over the same job.

This is a local prototype without authentication, tenant isolation or a complete
review-event audit. It does not automatically change contracts or determine legal
equivalence. Large collections can exceed search budgets: textual candidate
retrieval is a bounded full scan, not a scalable candidate index.

### Try it with synthetic documents

1. Upload and process [A-confidentiality.pdf](../examples/synthetic-contracts/A-confidentiality.pdf)
   and [D-delivery.pdf](../examples/synthetic-contracts/D-delivery.pdf).
2. Search for `The receiving party shall not disclose confidential information`
   at textual 100, then inspect confirmed and no-active-match document groups.
3. Process [P-printed-scan.jpg](../examples/synthetic-contracts/P-printed-scan.jpg)
   and compare OCR with the original.
4. Reveal automatic matches, explicitly confirm/dismiss/reset passages, reopen
   the saved search and export confirmed matches.

Technical references: [literal search](search.md), [textual retrieval](textual-search.md),
[semantics](semantic-search.md), [review workspace](review-workspace.md),
[saved runs](saved-search-runs.md) and [export formats](search-exports.md).

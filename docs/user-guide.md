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
7. [Find documents where a phrase was not found](#7-find-documents-where-a-phrase-was-not-found)
8. [Find and review similar wording](#8-find-and-review-similar-wording)
9. [Reopen searches and export results](#9-reopen-searches-and-export-results)
10. [Troubleshooting and limitations](#10-troubleshooting-and-limitations)

## 1. Start and stop the app

### Requirements and startup

You need the checked-out repository, Docker with Compose v2, and access to the
Docker daemon. Python, Node and Tesseract do not need separate host installations
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
edit the relevant values. For English and German OCR:

```dotenv
OCR_LANGUAGES=eng+deu
```

Both language packs are installed in the container; English alone is the default.
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

The worker uses PyMuPDF for PDFs and Tesseract for image OCR. The API uses character
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
4. Enable **Manual review required** for handwriting or difficult scans.
5. Choose **Save document**.

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
| Scanned PDF, or page containing images or too little embedded text | Render the entire page and run Tesseract OCR | Mixed text/image pages also use this conservative OCR path; recognition errors remain possible |
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

### Example: an old company name

To find `Oldname Ltd` in extracted contracts:

1. Upload and process the documents.
2. Choose **Literal search**.
3. Enter `Oldname Ltd` under **Text passage**.
4. Choose **Search mode: Normalized**.
5. Choose **Contain this phrase**.
6. Click **Run search**.

Search examines each document's latest revision and its selected extracted text.
Opening one document does not restrict Literal search to that document. The
visible library page does not restrict the searched collection either.

**Exact** matches the extracted character string including case, spaces and line
breaks. **Normalized** standardizes Unicode composition, case and whitespace;
`OLDNAME` followed by a line break and `Ltd` can therefore match `Oldname Ltd`.
Unicode casefolding can expand characters, such as German sharp s into `ss`.
Numbers, punctuation, hyphens and negations are preserved. `Oldname-Ltd` differs
from `Oldname Ltd`; line-end hyphenation is not repaired automatically. Both modes
search text, not company identities, word variants or legal meaning. They are not
regular-expression searches.

### Inspect results

**Documents found** shows matching documents with an evidence passage, context,
source and quality information. Open the offered page/document to view extracted
text in document details. Navigate additional result pages as needed. Literal
search returns documents and a first evidence occurrence, not a complete list of
every occurrence within each document.

Only ready documents appear in customer searches: complete coverage, usable text,
no unresolved quality/manual-review flags, and a completed current processing run.
Pending or problematic documents remain under **Manage documents**, outside the
search scope. They are not treated as negative results. Diagnostic API consumers
can still inspect the older full-scope classification; it is not a search UI list.

## 7. Find documents where a phrase was not found

### Example: a particular clause wording

Use this target phrase:

> The receiving party shall not disclose confidential information

1. Choose **Literal search** and enter the complete phrase under **Text passage**.
2. Use **Normalized** to ignore case/whitespace differences, or **Exact** to retain them.
3. Select **Do NOT contain this phrase**.
4. Choose **Run search**.
5. Inspect the negative results. Ineligible documents remain in Manage documents, outside this search scope.

**Documents without this phrase** contains ready documents whose full selected
text does not contain the submitted wording. Documents still being prepared are
not included and do not appear as an additional search-results group. Operators
can inspect them separately under **Manage documents**.

**“Phrase not found” does not mean “the legal clause is missing.”** Equivalent
wording may differ. Even text classified as fully processed can contain OCR errors.
Inspect originals and alternative formulations before making contractual decisions.

An unprocessed latest revision cannot borrow an older revision's clean text.
A pending or failed newer processing attempt also keeps the document outside new
ready-only searches. Existing saved searches retain their historical evidence.

Absence search has no semantic threshold. Failure to find a similar/semantic
passage is never turned into a negative clause finding.

## 8. Find and review similar wording

**Similar passages** finds positive candidates for variants, OCR errors or changed
wording, such as OCR reading `Oldname Ltd` as `Oldnarne Ltd`. It does not replace
absence search.

1. Open **Similar passages**, expanding **Search parameters** if necessary.
2. Optionally enter a **Search name**.
3. Enter **Text passage** and choose **Text comparison mode**.
4. Set **Minimum textual match**. For example, experiment with 85 and inspect
   results; 85 is not a universally safe threshold. 100 requires identical text
   in the chosen comparison mode.
5. Optionally enable **Compare meaning with local embeddings** and set
   **Minimum semantic match**.
6. Initially leave **Review status** at **All review states**.
7. To narrow scope, open a library document and enable **Search only the open document**.
8. Choose **Find passages**.

### Understand the thresholds

Textual retrieval scores character differences between the query and candidate
word windows, not the fraction of identical words. Textual 0 is not permitted.
Short or uninformative queries can yield poor matches even at relatively high
thresholds; expression-specific guidance explains the risk.

When enabled, semantics compares only the textually retrieved passages with the
query. Displayed context is not embedded. Both thresholds must pass; a related
paraphrase failing the textual threshold is not recovered by the semantic stage.

- Semantics off: no semantic computation or score.
- Semantic 0: calculate/display scores without discarding textual candidates.
- Semantic between 0 and 100: additionally filter by model similarity.
- Semantic 100: retain only identical comparison text under the product rule.

95% does not mean a 95% probability of correct meaning. A changed name, amount or
negation can be decisive despite high similarity. Inspect the displayed differences.
Overly broad searches can stop explicitly without a successful partial list.
Lengthen the query, raise the threshold or narrow scope before trying again.

### Navigate and review passages

A compact list appears beside one selected detail pane; on narrow screens the
panes are stacked. Details show textual/optional semantic scores, context and a
query/passage comparison. **View source text** or the page action opens preserved
extracted text. Download the original for the actual page image.

- **Previous passage / Next passage** crosses document boundaries.
- **Next unreviewed** advances within the current review-filtered view and wraps
  to its beginning when necessary.
- Use Up/Down or Home/End in the list. Tab reaches buttons; Enter/Space activates them.
- Collapse **Search parameters** to make room for reviewing.

| Decision | Meaning |
| --- | --- |
| **Not reviewed** | No decision yet, or explicitly reset |
| **Keep** | Retain this passage for the query |
| **Dismiss** | Reject this passage for the query |
| **Decide later** | Defer the decision |
| **Reset review** | Return a reviewed passage to Not reviewed |

The interface confirms a decision after a successful server response and advances
to the next passage. It stays at the last passage when there is no following item.
Failed saves leave selection and the previous decision intact.
**Final decisions** counts Keep + Dismiss; deferred/unreviewed passages remain
pending. Progress covers all stored similarity matches before review filtering.

**Review saved results** filters stored matches by current decision. A passage
leaving the filter disappears and the next remaining one is selected.
**Refresh reviews** reads decisions changed in other views and preserves the
selection when it still matches.

Decisions are shared in this local app without personal reviewer accounts.
Version checks prevent blind overwrites; refresh and reconsider after a conflict.
Keep/Dismiss do not change contract bytes, approve OCR quality or automatically
replace company names.

## 9. Reopen searches and export results

| Capability | Literal search | Similar passages |
| --- | --- | --- |
| Find literal wording | Yes | Yes, at textual 100 in the same mode |
| Explicit phrase-absence search over ready documents | Yes | No |
| Review every retained occurrence separately | No complete occurrence list | Yes |
| Keep / Dismiss / Decide later | No | Yes |
| Automatically saved durable search run | No | Yes, after success |
| CSV/JSON result export in the interface | No | Yes |

To turn a company-name finding into a durable occurrence review, submit the same
query/mode under **Similar passages** with textual 100. This creates another run;
it does not retroactively save the Literal search. Negative literal lists currently
have no equivalent save/export feature in the interface.

Successful Similar passages searches save all matches after similarity thresholds,
beyond visible list areas, together with the captured scope, scores and matching
source text.

- Open a run from **Saved searches** or bookmark its URL containing `search_run`.
- **Save name** changes its label, not its matches.
- Reopening reads stored results without new retrieval or embeddings.
- **Run again** creates a separate linked run using the original criteria against
  today's collection; the old run remains intact.
- To change criteria, edit parameters and choose **Find passages**.

Later uploads and OCR do not change an old run. Decisions remain editable, with
capture-time state also retained. New processing runs have new occurrence identities
and do not automatically inherit old decisions.

### Export

1. Open a saved run and expand **Export results**.
2. Select **Export review status**: all, Keep, Dismiss, Decide later or Not reviewed.
   This selector is independent of the on-screen filter.
3. Choose **Download CSV** or **Download JSON**.

Exports include all selected occurrences, not just the visible passage. Current
decisions are read at one consistent export snapshot. Search and export times are
separate. New ready-only runs contain no unsearchable documents. Historical exports retain
the original captured scope, including any older unsearchable records.

CSV is for spreadsheets. `row_type` distinguishes `summary`, `passage` and
`unsearchable` rows; filter to `passage` for a pure match list. Formula-like text
receives a leading apostrophe for spreadsheet safety. JSON preserves exact text,
comparison details, full captured scope and version/source references. Original
files are not embedded in result exports.

## 10. Troubleshooting and limitations

| Symptom | Check or action |
| --- | --- |
| Interface unavailable | Inspect `docker compose ps -a`, logs and `WEB_PORT` |
| 502 after replacing the API container | Run `docker compose restart frontend` to refresh Nginx's internal API address |
| Upload saved but no search text | Start processing; storage alone does not extract text |
| Job remains queued | Check the worker and `docker compose logs --tail=100 worker` |
| Incorrectly recognized words | Compare page text with the original; consider a better scan, appropriate OCR language and reprocessing |
| No positive match | Check mode, spelling, punctuation, hyphenation, revision and processing; consider Similar passages |
| Fewer negative results than expected | Inspect Manage documents for preparation issues; excluded documents are not confirmed negatives |
| Broad search stopped | Raise the threshold, refine wording or select one document under Similar passages; no successful partial list is returned |
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
2. Use the clause in section 7 for literal Contains and Not found searches.
3. Process [P-printed-scan.jpg](../examples/synthetic-contracts/P-printed-scan.jpg)
   and compare OCR with the original.
4. Find the phrase under Similar passages, review occurrences, reopen the saved
   run and export Keep matches.

Technical references: [literal search](search.md), [textual retrieval](textual-search.md),
[semantics](semantic-search.md), [review workspace](review-workspace.md),
[saved runs](saved-search-runs.md) and [export formats](search-exports.md).

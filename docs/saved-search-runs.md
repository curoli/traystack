# Saved search runs

**Similar passages → Find passages** automatically saves each successful search
with its full result set. **Search name** is optional; an unnamed run uses the
query as its name. **Saved searches** lists runs newest first. Opening one, or
opening its `?search_run=<uuid>` URL, loads stored results without running text
retrieval, normalization or embeddings again. Renaming changes only the label.

**Run again** creates a separate run against the current library using the
original query, comparison mode, thresholds, document selection and initial review
filter. It links to the previous run without replacing it. To change the search
criteria, edit the form and choose **Find passages** instead.

## What stays fixed

A successful run captures the complete positive candidate universe after the
textual and optional semantic thresholds, before review-state filtering and all
pagination. It includes every matching document and occurrence, not just the first
visible page. Frozen fields include:

- query, effective comparison text, thresholds, mode and submitted scope;
- selected revisions, processing jobs, source artifacts, titles and quality flags
  for every document in scope, including unmatched and unsearchable documents;
- scores, raw semantic cosine, scorer/library/candidate-policy versions and
  model/pipeline provenance when semantics was enabled;
- matched text, offsets, page references, surrounding context and text differences;
- search timestamp, warnings, query guidance and review state at capture.

**Documents at capture** shows the captured scope. **View source text** opens the
archived extraction for that result, with page text and original processing/quality
metadata. Reprocessing, adding documents, changing titles or publishing another
revision does not change these results or silently substitute today's text.
Original downloads still use the immutable source artifact.

This feature covers the positive **Similar passages** workflow. Literal/negative
**Run search** and `POST /api/search/textual` remain read-only ephemeral searches.
Stored positive results are not proof of absence or legal equivalence.

## Reviews remain editable

Reviews are shared current annotations, not immutable result scores. **Review
saved results** changes the view over the stored candidate universe; **Refresh
reviews** reads the latest decisions. Neither starts a new search. Counts before
review filtering cover the stored similarity matches. A filtered view may change
as decisions change; the underlying matches, scores and sources do not.

Each occurrence exposes both `review` (current) and `review_at_capture` (historical).
Keep, Dismiss, Decide later and Reset review remain available after reprocessing.
Historical writes supply `search_run_id` and are validated against membership in
the frozen run, its source identity, offsets and archived text fingerprint. Existing
live review writes still require the currently selected source. Both paths use the
same optimistic version checks, so one view cannot blindly overwrite another.
A new processing run has new occurrence IDs and does not inherit old decisions.
There are no reviewer accounts or complete review-event audit history.

## Export

**Export results** downloads the full run as CSV or JSON with an independent
review-state filter. Current decisions are read in one export snapshot, while
matching text, scores and source identities remain frozen. Unsearchable documents
are always separate. See [search-exports.md](search-exports.md) for formats,
provenance, spreadsheet handling and the API.

## Storage and consistency

Migration `0004` adds `search_runs`, `archived_texts` and `search_run_sources`.
Retrieval and capture use one PostgreSQL REPEATABLE READ, read-only transaction.
After that snapshot is complete, a separate transaction atomically persists the
run and its source associations. An aborted or failed search stores no run or
partial source archive. Publication of newer text between capture and persistence
is safe: the captured payload is already independent of mutable selected text.

Source text is archived once per processing-job ID and reused across searches.
An unexpected different payload for an existing job is rejected. Archives retain
raw/normalized full text, page text/offsets, extraction methods, confidence and
quality metadata. Unused layout/bounding-box arrays are not duplicated; original
derivative artifacts remain available. Only jobs with retained similarity matches
need text archives; all scoped document metadata is retained regardless of match.

Canonical JSON SHA-256 checks cover the immutable request, scope and result. Source
archives have independent checksums. Reads fail explicitly if the stored version
or content is invalid, rather than rerunning a search or substituting current text.
These checks detect accidental corruption; they are not a signed audit log.

The existing text/semantic work and candidate budgets still apply. Saved captures
also default to 64,000,000 serialized bytes (scope, results and archived sources)
and 10,000 scoped documents. Configure `SEARCH_SNAPSHOT_MAX_BYTES` and
`SEARCH_SNAPSHOT_MAX_DOCUMENTS` on the API. Exceeding either returns a structured
422 incomplete-results error, without a saved partial run. There is no silent
truncation. Limits bound each capture, not total storage across runs. The local
prototype retains runs indefinitely and has no delete/retention UI; backup the
PostgreSQL database together with artifact storage.

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/search-runs` | `{search: <TextualSearchRequest>, name?, parent_run_id?}`; capture and return first view (201) |
| `GET /api/search-runs?limit=20&offset=0` | Metadata-only history, newest first |
| `GET /api/search-runs/{id}` | Stored result view, current review overlay |
| `GET /api/search-runs/{id}/scope` | Captured scope, including nonmatches |
| `POST /api/search-runs/{id}/name` | Rename with `{name: "..."}` |
| `GET /api/search-runs/{id}/sources/{job_id}` | Archived text, only for member sources |

Stored result views accept `limit`, `offset`, `occurrence_limit`,
`occurrence_offset`, `document_id`, `review_filter`, `unsearchable_limit` and
`unsearchable_offset`. A document restriction must belong to the saved scope;
occurrence paging requires a document. These parameters change only the view,
never the saved query, scores or scope. Captured criteria are echoed alongside
`run_id`, `run_name`, `parent_run_id`, `scope_total` and `captured_review_filter`.

Migration upgrade/downgrade should be exercised only on a disposable database.
Downgrading `0004` deletes saved runs and archives, while preserving source
artifacts and passage-review records. The normal app should only be upgraded.

## Validation

The backend regression cases cover complete multi-page snapshots, zero results,
metadata/library/reprocessing changes, revision publication between capture and
persistence, archived text identity and deduplication, source membership, integrity
failures, cap/model failures without partial persistence, historical review writes
and current review overlays. Reopening tests fail if retrieval or the model is
called. Multi-page coverage includes 28 matching documents, 168 occurrences and
12 unsearchable documents.

The two new browser scenarios use the real API and database. They check bookmarks,
rename/history, historical text and editable reviews after real reprocessing,
filtering without a new search, a linked rerun with new matches, and preserved
real model scores while new-search endpoints are blocked. Existing review,
pagination, late-response, semantic and source-navigation scenarios remain covered.
The English saved-run and source views were inspected at desktop and 390px widths.

Final checks: 197 backend tests against isolated PostgreSQL with real OCR and the
pinned embedding model, all 28 Playwright/Chrome scenarios, TypeScript/Vite, Ruff,
Prettier, dependency consistency, local documentation links and diff checks passed.
Migration `0004` passed metadata comparison and downgrade/upgrade on the disposable
database; the normal app received only the additive upgrade.

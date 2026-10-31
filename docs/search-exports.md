# Exporting saved passage searches

Open a saved run in **Similar passages**, expand **Export results**, select
**Export review status**, then choose **Download CSV** or **Download JSON**.
The independent export selector offers All review states, Keep, Dismiss, Decide
later and Not reviewed. It defaults to All; it does not change the result view.
Unsubmitted search-form edits do not change the export.

Each download covers the complete saved run and selected current review state,
including passages beyond every document/occurrence page. It never runs retrieval
or embeddings again. Captured query, thresholds, scope, scores, source identity,
text, offsets and comparison versions stay fixed after library changes or
reprocessing. Reviews are read at export time; each passage also retains its
`review_at_capture` state. Search and export timestamps are separate UTC values.

Every export uses one PostgreSQL REPEATABLE READ, read-only transaction, so a review
saved by another view during the download cannot mix two review states. A later
export can reflect that new decision. Exports do not create runs, reviews or
artifacts. A corrupt stored snapshot fails with an error, rather than producing a
partial file or substituting a fresh search. UI errors leave the result list
intact; replacing the run cancels its pending browser download.

## CSV

CSV uses UTF-8 with a byte-order mark for spreadsheet imports, comma separators,
quoted fields and CRLF row separators. Quoting preserves commas, quotes and
multiline context. Scores are the saved numeric values, without UI rounding.
Semantic cells are empty when semantic comparison was disabled.

The `row_type` column distinguishes:

- `summary`: one row carrying query, run identity/name, timestamps, thresholds,
  counts, comparison versions and search warning codes, even for zero matches;
- `passage`: one row per selected occurrence, including document/revision/source
  IDs, page references, offsets, matched text, context, both scores and current
  and captured review states/versions/timestamps;
- `unsearchable`: one row per document that could not be searched at capture,
  including its available provenance and warnings, regardless of review filter.

Shared run metadata is repeated on each row so filtered spreadsheet rows retain
provenance. `exported_documents` and `exported_passages` describe the chosen review
filter. `scope_documents` includes the whole original selection, and
`unsearchable_documents` is separate. These counts are not proof of clause absence.
Document quality, warning codes and a positive-search notice travel with the file.
A scope containing unmatched searchable documents is fully represented in JSON;
CSV does not add rows for those documents.

Text fields whose first non-space/control character is `=`, `+`, `-` or `@` are
prefixed with an apostrophe to prevent spreadsheet formula evaluation. This is an
intentional CSV-only transformation; use JSON for exact original text. Numeric
values, including negative model cosines, remain numbers.

## JSON

The versioned envelope (`schema_version: 1`) contains:

| Field | Contents |
| --- | --- |
| `exported_at` | Export snapshot time in UTC |
| `reviews`, `notice` | Review timing and positive-search interpretation |
| `run` | ID/name, parent, search/creation times, original candidate counts, snapshot version/hash |
| `request` | Captured search request, including the initial review filter and original page parameters |
| `captured_scope` | Every document at capture, including unmatched/unsearchable documents |
| `result` | Frozen search metadata, full selected matches, unsearchables, current counts and reviews |

`result.review_filter` is the export selection; the filter in `request` remains
the original one. View-pagination fields are removed from `result` and its groups.
All matched text, context, Unicode code-point offsets, text differences, raw model
cosines, semantic provenance and review data retain their saved precision and
structure. The SHA-256 is a reference to the original immutable snapshot, not a
checksum of the exported file or its current review overlay.

Source IDs in result documents refer to immutable artifacts and archived processing
runs. Original bytes and full archived extractions are not embedded in these
exports: use the original download or
`GET /api/search-runs/{run_id}/sources/{processing_job_id}`. The JSON file is a
portable result record, not a complete database/artifact backup or review-event
audit trail.

## API

`GET /api/search-runs/{id}/export?format=csv&review_filter=all`

`format` accepts `csv` (default) or `json`. `review_filter` accepts `all` (default),
`keep`, `dismiss`, `later` or `unreviewed`. Export is always complete for the saved
scope; it has no pagination or alternative-query parameters. Invalid formats or
filters return 422, an unknown run 404, and failed snapshot integrity 503.

Successful responses are attachments named
`traystack-search-{id}-{review_filter}.{format}` with `Cache-Control: no-store`.
The route uses the existing bounded saved snapshots; no new migration, dependency,
external service or model access is needed.

## Validation

215 backend tests passed with isolated PostgreSQL, real Tesseract OCR and the
pinned embedding model. Export regressions cover 28 matching documents with 168
occurrences and 12 unsearchables beyond pagination, all review filters, empty
results, preserved semantic precision/versions, actual reprocessing, concurrent
review writes, corrupt snapshots and CSV quoting/Unicode/formula handling.

All 30 Playwright/Chrome scenarios passed. The two new export scenarios download
and inspect real files, retain captured criteria despite unsubmitted form edits,
exercise saved semantic scores, and check failure recovery and a delayed export
superseded by a new search. Desktop and 390px mobile views were inspected; the
long saved-run heading now wraps without horizontal overflow. TypeScript/Vite,
Ruff, Prettier, dependency consistency, schema comparison, documentation links and
diff checks passed. No database migration was needed.

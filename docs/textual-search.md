# Textual similarity and multiple occurrences

The **Similar passages** workflow is positive candidate retrieval, separate from
**Literal search** and its exact/normalized absence checks. An optional
[semantic comparison stage](semantic-search.md) now scores and filters these
textual candidates. [Saved reviews](passage-reviews.md) add per-occurrence
decisions, status filters and counters after similarity filtering. Neither
similarity stage nor review state establishes clause absence.

## User workflow

1. Choose **Similar passages**, enter a text passage and select **Normalized** or
   **Exact** comparison mode.
2. Set **Minimum textual match** to a value greater than 0 and at most 100.
   Inspect the expression-specific guidance, then choose **Find passages**.
   To narrow the scope, open a document in the library and enable
   **Search only the open document**.
3. Inspect results grouped by document, ordered by each document's best score.
   Each occurrence shows its score, surrounding text, page references, original
   download and a side-by-side comparison with changed words/punctuation marked.
4. Page through occurrences within a document and open the relevant source page
   or logical text section. Quality warnings remain visible on candidate matches.
5. Rerun the search after processing changes. An occurrence page from a newer
   selected run is rejected in the UI instead of being mixed into the old results.

Only the latest revision per document is searched. No text from an older revision
is substituted if the latest one has not been processed. Sources with partial or
review-required text may produce warned candidates. Documents without usable
selected text, or with unsupported normalization in normalized mode, are listed
separately as **Unsearchable**. Unmatched but searchable documents are counted,
without claiming their clauses are absent or their extraction is trustworthy.

## Score contract

For query `q` and the **displayed matched passage** `p`:

```text
score = 100 × (1 − LevenshteinDistance(q, p) / max(length(q), length(p)))
```

Insertions, deletions and substitutions each cost one Unicode code point. RapidFuzz
implements the distance locally; there is no network model call.
[Official normalized Levenshtein documentation](https://rapidfuzz.github.io/RapidFuzz/Usage/distance/Levenshtein.html#normalized-similarity).

- **100** requires identical text after the selected mode's transformation.
  Exact mode preserves the source string; normalized mode uses the same versioned
  NFC/whitespace/casefold rules as the existing literal search. It preserves
  digits, punctuation, hyphens and negations.
- **0 is rejected**, in both the UI and API. The textual filter cannot be disabled.
  Positive fractional scores are supported; there is no claimed universal safe
  lower percentage. Query-dependent warnings and runtime limits constrain broad searches.
- **Values greater than 0 and below 100** are minimum character-similarity scores,
  not confidence, a probability,
  or semantic/legal equivalence. Identical phrases can also occur in negated or
  otherwise different surrounding contexts, so context and original remain relevant.
- Filtering and ranking use the unrounded score. The API returns four decimal
  places; the UI displays two. The maximum query length is 500 code points, so
  a one-character difference cannot be rounded into a displayed 100.00% score.
- Query and passage are compared in the same mode as the displayed diff. A
  normalized comparison may differ in spelling/case from the original page view;
  no guessed normalized-to-raw character mapping is used.

## Expression-specific guidance

The initial input value 85 is a demonstration starting value, not an approved
threshold. A debounced `POST /api/search/textual/assess` call evaluates the current
query, mode and positive threshold without searching the collection or writing
anything. The actual search repeats exactly the same assessment; submitted
criteria have their own immutable guidance in the result snapshot. Old assessment
requests are discarded when the expression changes.

The versioned `query-risk-v1` assessment reports the effective comparison string,
comparison length, alphanumeric content length, word-chunk count and an
**equal-length edit illustration**:

```text
floor(comparison length × (100 − minimum score) / 100)
```

For example, 80% permits two edits in a ten-character equal-length passage and
twenty in a hundred-character passage. This is not a universal edit limit:
longer/shorter candidate passages can permit a different number of edits. Decimal
arithmetic keeps the illustration accurate, including very small positive scores.

The heuristics warn about:

- Fewer than eight alphanumeric characters, including at exact score 100.
- Short expressions with fewer than twelve letters/digits when the threshold
  permits an equal-length edit or a one-character insertion into a longer passage.
- Expressions composed entirely of a small English/German common-word list;
  none of those words is removed from matching.
- Punctuation-only and predominantly numeric expressions (digits are at least
  half the alphanumeric content).
- Large illustrative edit budgets: at least three edits and either a threshold
  below 75 or at least twenty permitted equal-length edits.
- One-/two-word expressions with at least eight letters/digits and a score below 85.

These are explicit usability heuristics, **not calibrated false-positive rates,
a learned minimum threshold, or a guarantee of readable/legal matches**. Matching
still uses every character under the selected mode. The app never silently raises
the user's threshold. Each approximate match continues to caution about changed
names, amounts, deadlines and negations even at high scores.

## Candidate and overlap policy

This prototype scans complete selected text to generate positive candidates:

1. Find every non-overlapping exact substring occurrence anywhere in the full
   query-mode text. This includes within-word matches and supported page/line
   crossings. A query `ana` in `banana` yields one non-overlapping occurrence.
2. Below threshold 100, also enumerate contiguous `\S+` word windows. If the query
   has `n` words, consider lengths from `max(1, n − max(2, ceil(n/2)))` through
   `n + max(2, ceil(n/2))`. For a text shorter than the minimum window, consider
   the whole shorter text. Whitespace inside each window is retained in exact mode.
3. Score the full windows and retain the highest-scoring qualifying window per
   word start (shortest end wins ties). Combine these with all literal occurrences.
   Order by descending score, earliest start, then earliest end. Greedily keep non-overlapping spans;
   identical literal occurrences therefore take priority over nearby approximate
   windows. Adjacent spans can both remain.

This removes near-duplicate windows but **does not enumerate every possible
approximate character substring**. Very different-length paraphrases and
word-internal fuzzy fragments can be missed. Even a returned document may have
additional candidate variants removed by per-start selection or overlap consolidation. The API names
the candidate policy and scorer version explicitly; counts refer to retained
occurrences under that policy, not every conceivable text interval.

There is no trigram candidate index or semantic reranking. The optional semantic
stage filters existing candidates and preserves textual ranking. A
future index must be evaluated for recall rather than silently restricting what
a negative search is allowed to examine.

## API

```sh
curl --fail http://localhost:8000/api/search/textual \
  -H 'Content-Type: application/json' \
  -d '{"query":"The receiving party shall not disclose confidential information","mode":"normalized","minimum_score":85,"scope":"latest","limit":10,"occurrence_limit":5}'
```

`POST /api/search/textual` accepts:

| Field | Rule |
|---|---|
| `query` | 1–500 characters, nonblank, valid Unicode, no NUL |
| `mode` | `exact` or `normalized` |
| `minimum_score` | Finite number, greater than 0 and at most 100; default 85 |
| `scope` | `latest` only |
| `document_id` | Optional UUID to search one document |
| `limit`, `offset` | Document pagination, limit 1–25, default 10 |
| `occurrence_limit` | Retained occurrences per document, 1–25, default 5 |
| `occurrence_offset` | Nonnegative; nonzero requires `document_id` |
| `unsearchable_limit`, `unsearchable_offset` | Separate unavailable-document pagination, default limit 10, max 100 |

Unknown fields, unsupported modes, zero/negative/nonfinite thresholds and invalid
pagination return 422. There is no `lacks` relation here: use the unchanged
`POST /api/search` contract for literal absence.

The response echoes `document_id` (or null for the whole collection), includes
`assessment` and complete-result `result_warnings`, and reports global scope counts
before pagination, documents with
candidate occurrences and independently paged unsearchable documents. Each group
contains source/revision/selected-job identity, coverage, quality/warnings, and
its own occurrence count/offset/limit. Each occurrence includes:

- Score, matched text and Unicode-code-point offsets (zero-based, end exclusive).
- Snippet and its start offset in the same raw/normalized text.
- Available page numbers, labeled as physical, logical or unavailable. Empty
  normalized page spans are not claimed as locations. TXT/HTML use logical pages.
- A word/punctuation/whitespace diff that reconstructs the effective query and
  found passage exactly. Highlighting is textual; it makes no legal judgement.
- An occurrence hash bound to selected job, query/mode, scoring/candidate policy
  and offsets. This is an identity for this processing run, not a stored review decision.

`REPEATABLE READ` and a read-only transaction keep scope, text, provenance and page
locations in one snapshot. Paging is a new snapshot, including per-document
occurrence paging; the UI checks the selected run before replacing a page of
matches. Form edits do not change the submitted criteria used for pagination.

The scope and selected-run warnings are shared with the existing literal search.
No source text is logged. The original API retains its first-occurrence policy,
negative eligibility and independent unverifiable pagination.

## Resource and performance limits

All selected text is scanned in this prototype; it is streamed in small document
batches, but retained matching text/candidates remain in memory for grouping and
pagination. It has not been benchmarked as a production-scale search service.

There are separate **processing** and **review-breadth** limits. Processing limits
remain 20 million text code points, two million candidate windows and 100,000
per-start/literal intervals before overlap consolidation. Review-breadth limits
count actual retained, non-overlapping passages:

| Condition | Prototype limit / behavior |
|---|---|
| Passages in one document | Stop when more than 250 qualify |
| Passages across the selected documents | Stop when more than 2,500 qualify |
| Dense approximate results | Below threshold 100, stop at 100 or more retained passages with density at least 20 per 1,000 full comparison-text characters |
| Broad completed results | Warn at 500 total passages or 50 in one document; the result is complete if no stop limit was reached |

These are review/workload policies for this prototype, not empirically calibrated
legal-risk boundaries. Density is measured against the document's whole selected
comparison text, not a local sliding window. Exact score 100 is exempt from density
alone, but count and processing limits still apply. Pagination does not bypass limits.

During literal scanning, non-overlapping exact occurrences already establish a
lower bound on retained hits, so overflow stops before approximate comparisons.
For approximate windows, the retained count is checked while overlap consolidation
progresses, and against the completed counts from previous documents. Raw overlapping
windows alone do not trigger the review-breadth limits; independent processing
budgets still protect candidate generation.

Every stop rejects the **whole request with HTTP 422**. It returns no successful
summary, snippets or partial result list:

```json
{
  "detail": {
    "code": "textual_search_aborted",
    "reason": "document_passage_limit",
    "message": "Too many candidate passages in one document. Increase textual similarity or use a more specific expression.",
    "resource": "retained_passages_in_document",
    "limit": 250,
    "observed_at_least": 251,
    "documents_inspected": 1,
    "results_complete": false
  }
}
```

Other reasons are `total_passage_limit`, `dense_passages` and `work_limit`.
`observed_at_least` and `documents_inspected` are partial observations at stopping,
not collection totals. The UI explains the reason/action, clears earlier search
results even if stopping occurred during pagination, and preserves the entered
threshold. Users can add context, raise the threshold themselves, or narrow to
the open document. Submitted document scope is preserved during pagination even
if the live form or open document changes.

A stop is automatic server-side budget enforcement, **not a user-cancellable
background-job system**. Successful searches still use the declared candidate
policy rather than exhaustive approximate character-substring enumeration.
The earlier filter-off/0 performance experiment is historical: 0 is no longer a
supported API or UI value. Measure larger collections before adding an index;
no database migration or runtime dependency was needed for these controls.

## Measured training evaluation

Reproduce with locked dependencies:

```sh
.venv/bin/python scripts/evaluate_textual_search.py --output data/textual-evaluation.json
```

Add `--include-details` for every evaluated pair; the committed
[training report](../examples/synthetic-handwriting/textual-evaluation-train.json)
keeps aggregate counts plus missed-positive IDs and representative nonliteral
candidates. It records the source-corpus and OCR-report hashes, RapidFuzz version,
scorer and candidate policy. It now evaluates only positive thresholds. It compares 70 original training texts and the 45
**actual OCR outputs already measured** in the earlier image evaluation. It does
not rerun OCR or insert transcriptions into application text. Dev/test remain untouched.

| Minimum score | Literal positives recovered from OCR | Materially changed candidates also returned |
|---|---:|---:|
| 100 | 12/18 | 0/9 |
| 95 | 17/18 | 3/9 |
| 90 | 18/18 | 6/9 |
| 85 | 18/18 | 9/9 |

The matching task in this table uses source-literal labels: a modified amount or
negation is not an OCR spelling error. Nonliteral candidates are a review burden,
not automatically evidence of an algorithm failure or equivalent meaning. The
report's literal precision is explicitly a proxy for this narrow task. The small,
selected font-simulation training sample is **not a held-out accuracy claim**,
a legal benchmark or a universal threshold recommendation.

## Verification

On 30 October 2026, all **164 backend tests** passed against isolated PostgreSQL
with real OCR. New controls checks cover exact edit arithmetic, short/common/numeric
expressions, normalization, positive fractional scores and rejection of 0,
assessment/search agreement, early literal overflow, non-overlap counting, density,
global overflow, narrow-scope echo and complete-result warnings. Aborts have no
partial success fields and do not change the literal absence workflow.

All **18 Playwright/Chrome scenarios** passed, including real overflow at 251
passages, refinement after an abort, blocked zero, real UI document scoping and
exact mode. An isolated pagination-error test checks that an aborted occurrence
request clears the old result snapshot. A delayed-error regression also verifies
that a superseded pagination request cannot clear a newer search's results;
abort callbacks are bound to the originating search request ID. Successful
workflows use the real stack.
TypeScript/Vite, Ruff, Prettier, dependency consistency, Markdown links and
`git diff --check` are checked. The known Starlette/HTTPX TestClient warning remains.

# Textual similarity and multiple occurrences

The **Similar passages** workflow is positive candidate retrieval, separate from
**Literal search** and its exact/normalized absence checks. It adds no semantic
scores, embeddings or review decisions yet. It never establishes clause absence.

## User workflow

1. Choose **Similar passages**, enter a text passage and select **Normalized** or
   **Exact** comparison mode.
2. Set **Minimum textual match**, from 0 to 100, and choose **Find passages**.
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
- **0** disables the score filter: every nonempty supported selected text has a
  candidate, even when it is unrelated. Documents without searchable text still
  cannot produce an invented passage.
- **1–99** is a minimum character-similarity score, not confidence, a probability,
  or semantic/legal equivalence. Identical phrases can also occur in negated or
  otherwise different surrounding contexts, so context and original remain relevant.
- Filtering and ranking use the unrounded score. The API returns four decimal
  places; the UI displays two. The maximum query length is 500 code points, so
  a one-character difference cannot be rounded into a displayed 100.00% score.
- Query and passage are compared in the same mode as the displayed diff. A
  normalized comparison may differ in spelling/case from the original page view;
  no guessed normalized-to-raw character mapping is used.

The initial input value 85 is a demonstration starting value, not an approved
threshold. Inputs below 70 warn about unrelated candidates, 0 explicitly warns
that filtering is disabled, and effective queries shorter than eight characters
warn about limited context. These are usability heuristics, not calibrated error
rates. Each approximate match also cautions that names, amounts, deadlines or
negations may have changed even at a high score.

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

There is no trigram candidate index or semantic ranker in this increment. A
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
| `minimum_score` | Finite number, inclusive range 0–100; default 85 |
| `scope` | `latest` only |
| `document_id` | Optional UUID to search one document |
| `limit`, `offset` | Document pagination, limit 1–25, default 10 |
| `occurrence_limit` | Retained occurrences per document, 1–25, default 5 |
| `occurrence_offset` | Nonnegative; nonzero requires `document_id` |
| `unsearchable_limit`, `unsearchable_offset` | Separate unavailable-document pagination, default limit 10, max 100 |

Unknown fields, unsupported modes, negative/nonfinite thresholds and invalid
pagination return 422. There is no `lacks` relation here: use the unchanged
`POST /api/search` contract for literal absence.

The response reports global scope counts before pagination, documents with
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

A request may inspect up to 20 million text code points, two million candidate
windows and 100,000 retained per-start/literal candidate intervals (before overlap consolidation). If any
work budget is exceeded, the **whole request fails with 422** and a visible error;
there are no quietly truncated results or absence claims. Raising the threshold
or using `document_id` can reduce work. Threshold 100 skips approximate windows.
For larger imported collections, measure end-to-end latency and memory before
choosing an index or further optimization. There is no database migration.

A one-shot local smoke check on 136 stored documents (75 searchable) measured
about 84 ms at threshold 100, 240 ms at 85 and 473 ms at 0, including HTTP/JSON via
Nginx. At 0, all 75 searchable documents qualified. This mixed demo/test collection
is not a production benchmark and gives no percentile, concurrency or scale guarantee.

## Measured training evaluation

Reproduce with locked dependencies:

```sh
.venv/bin/python scripts/evaluate_textual_search.py --output data/textual-evaluation.json
```

Add `--include-details` for every evaluated pair; the committed
[training report](../examples/synthetic-handwriting/textual-evaluation-train.json)
keeps aggregate counts plus missed-positive IDs and representative nonliteral
candidates. It records the source-corpus and OCR-report hashes, RapidFuzz version,
scorer and candidate policy. It compares 70 original training texts and the 45
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

On 30 October 2026, all 149 backend tests passed with PostgreSQL and real OCR,
including upload → OCR → textual search, multiple occurrences, Unicode/empty-page
spans, independent pagination, budget rejection, latest-revision/quality behavior,
and concurrent publication during a consistent search snapshot. All 15 existing
and new Playwright/Chrome scenarios passed; after the final candidate-memory
optimization the two new textual workflows were rerun successfully. They cover
context/diffs, submitted criteria, repeated page navigation, source-run changes,
zero/exact thresholds, server warnings and mobile overflow.

TypeScript/Vite, Ruff, Prettier, dependency consistency, local Markdown links and
`git diff --check` were checked. The ORM/migration check found no schema changes.
The known Starlette/HTTPX TestClient deprecation warning remains.

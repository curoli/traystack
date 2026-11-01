# Full-text search — milestone 3

`POST /api/search` checks all selected text from the **latest revision of each
document**. An unprocessed newer revision never falls back to an older index.
Documents without revisions are also unverifiable.

```json
{
  "query": "The receiving party shall not disclose confidential information",
  "mode": "normalized",
  "relation": "lacks",
  "scope": "latest",
  "limit": 25,
  "offset": 0,
  "unverifiable_limit": 25,
  "unverifiable_offset": 0
}
```

## Result meanings

| Status | Meaning |
| --- | --- |
| `found` | Passage occurs in selected text; positive findings retain quality warnings |
| `not_found_in_processed_text` | Absent from all selected text, with complete coverage and no known quality issue |
| `unverifiable` | Missing text, insufficient coverage/quality or unsupported normalization rules |

`contains` returns positives in `results`; `lacks` returns negatives. Both separately
return `unverifiable`. Independent offsets/limits never change classification or
global `summary` counts. An empty first result group does not prove all documents
were examined reliably.

A source or subsequent same-source run's manual flag prevents negative findings,
even if an older clean text remains selected. Failed/pending newer runs are shown
beside the actual selected run. Valid older text may remain selected with explicit
provenance; this differs from falling back to an older revision.

## Literal matching and normalization

- `exact`: unchanged substring in `revision_texts.plain_text`, including case and
  line breaks. Raw pages are separated by `\n\f\n`.
- `normalized`: the same versioned NFC/whitespace/casefold function as processing.
  Numbers, negation, punctuation and hyphens remain; nonempty pages join with a space.
- PostgreSQL `strpos` examines full text with bound parameters. Percent signs,
  underscores, backslashes and SQL-like input are ordinary text. No top-k or segment
  cutoff decides absence.
- Unsupported normalization yields `unverifiable` in normalized mode; exact raw
  search remains possible independently.

Input is 1–2000 characters, nonblank. NUL, invalid Unicode, unknown fields, fuzzy
mode, `scope: all` and invalid pagination return 422. Validation identifies fields
and reasons without reflecting input contents.

## Evidence and provenance

Each document returns the first occurrence in its newest revision
(`match_policy: first_occurrence_per_revision`). `total` counts documents, not
occurrences. Positives include matched text, snippet, original artifact, selected
job, engine versions, quality and available pages. Negatives/unverifiables invent
no occurrence or offsets.

Offsets are zero-based Unicode code points with exclusive ends. `offset_basis`
is `plain_text` or `normalized_text`; `snippet_start_offset` uses the same string.
JavaScript highlighting handles code points rather than UTF-16 units.
`page_numbers` and start/end pages can span multiple pages. Raw mappings use exact
page lengths/separators; normalized mappings use stored offsets. Unknown page
positions are not guessed. `score` is null.

The UI opens selected-run page text. Reprocessing prompts another literal search
rather than reattaching old evidence to new text. Displayed results are explicitly
labelled snapshots until the next search; durable positive saved runs are separate.

## Consistency and limitations

Counts, snippets, provenance and page references share one read-only REPEATABLE
READ transaction. Integration coverage publishes new text between queries and
checks that the original coherent result remains; concurrent workers cannot mix
another run's pages into the response.

The prototype scans selected full text in PostgreSQL and loads scope-wide metadata;
snippets/pages are loaded only for returned positives. Large collections need query
plan and server aggregation/pagination work. This milestone added no migration.
The separate [textual API](textual-search.md) adds multiple scored positives; the
optional [semantic stage](semantic-search.md) does not change this literal/absence
contract.

Findings concern extracted text, not legal completeness or perfect OCR. Sources
processed with older faulty extraction need reprocessing; search itself never
extracts again or replaces required human review.

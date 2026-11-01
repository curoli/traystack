# Search-ready documents and automatic review navigation

The readiness rules below still apply. The literal-search interface and automatic
review advancement described here are historical. For the current interface,
three-state review and explicit passage navigation, use the
[unified workflow](unified-review.md) and [user guide](user-guide.md).

The search interface is separate from document preparation. **Manage documents**
is collapsed by default and contains upload, processing, quality checks and job
history. Search users see results from ready documents, without an unsearchable or
unverifiable list. A document absent from the search library is not a negative hit.

## Readiness

The UI submits `ready_only: true` for literal searches and newly created saved
passage searches. The server applies readiness before searching, counting, capturing
scope or spending textual/semantic budgets. Eligibility requires:

- the latest revision, with nonempty usable selected text;
- complete coverage and `no_known_issue` quality;
- a completed selected job that is also the latest job;
- no manual-review requirement on the source or a same-source processing run;
- supported normalization when normalized comparison is requested.

Pending, failed, partial and flagged sources stay in document management. This
conservative rule also excludes flagged HTML/handwriting; the app does not invent
an automatic quality approval or silently clear persistent review flags. A newer
pending/failed processing attempt makes that document unavailable to new ready-only
searches until a suitable result is published. An unprocessed new revision never
borrows its predecessor's text.

For backward-compatible diagnostic integrations, the API's `ready_only` field
currently defaults to false. Existing full-scope API classification remains
available; customer-facing UI requests always opt into the ready-only scope.
Search returns no hidden partial lists: totals describe the selected scope.

Existing saved searches remain immutable, including historical scope and source
records. Opening them does not rerun current readiness selection. Run again in the
interface creates a new ready-only search. New runs no longer capture ineligible
sources; historical exports retain their original evidence.

## Finding documents without a phrase

Under **Literal search**, the **Find documents that** radio group offers:

- **Contain this phrase**;
- **Do NOT contain this phrase**.

Enter the phrase and choose **Run search**. The second option produces **Documents
without this phrase**, using full selected text rather than a missing fuzzy or
semantic candidate. It checks the submitted wording, not whether an equivalent
legal clause exists. Exact/normalized comparison rules remain unchanged.

Literal evidence opens in a text-only reader, without processing controls. Document
preparation remains in Manage documents. Saved source text similarly keeps technical
provenance behind an optional Source details disclosure.

## Review advancement

After a confirmed Keep, Dismiss, Decide later or Reset review save, selection moves
to the following occurrence. In a filtered view, removing a passage selects the
next remaining occurrence at its position, or the previous one at the end. At the
last passage of an All view, selection remains there; there is no fabricated next
item or automatic wrap. Next unreviewed remains available for explicit wrapping.
Failures/conflicts keep the current passage and prior decision. Navigation is
locked during the write and obsolete callbacks cannot alter replacement searches.

## Validation

218 backend tests passed against disposable PostgreSQL with real OCR and the
pinned local embedding model. New regressions verify ready-only positive/negative
and textual searches, capture scope, exclusion of pending/partial/flagged/blank
sources, and pending reprocessing without changing the diagnostic API contract.

All 33 browser scenarios passed against an isolated Compose app. Eight focused
review/navigation cases passed again after the final focus/scroll refinement.
The new customer-flow scenario checks collapsed management, explicit absence,
no unsearchable results, automatic advancement after confirmed decisions, failure
retaining the selected passage, and source-view cleanup/focus during advancement.
Existing processing, historical snapshots, exports, stale-source and late-write
checks passed with their updated UI paths. Desktop and 390px mobile views were
inspected without horizontal overflow. TypeScript/Vite, Ruff, Prettier, dependency
consistency, schema comparison and documentation/diff checks passed. No migration
was added; original app records and historical runs were preserved.

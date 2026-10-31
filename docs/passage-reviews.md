# Saved passage reviews

**Similar passages** supports **Keep**, **Dismiss** and **Decide later** for each
individual passage. **Not reviewed** is a distinct initial state. **Reset review**
returns a reviewed passage to that initial state. Decisions persist in PostgreSQL
through page reloads, new searches and application restarts; they are shared in
this local app, rather than assigned to separate reviewer accounts.

## Workflow

1. Run a textual search, optionally with the semantic filter enabled.
2. Inspect the matched passage, surrounding context, source and text differences.
3. Choose a decision in **Review this passage**. The UI displays the new state and
   saved timestamp only after the API confirms the write. Failures leave the prior
   displayed decision intact and show an error beside that passage.
4. Use **Review saved results** to filter the stored result list without a new search.
   All states, Not reviewed, Keep, Dismiss and Decide later are separate choices.
5. Change a decision or choose **Reset review** whenever needed.

The four counters cover every passage passing the submitted textual and semantic
thresholds in the selected scope, **before** the review filter and pagination.
Document/occurrence totals and result pages describe passages passing the review
filter too. Unsearchable documents remain a separate group. A status filter never
turns a missing positive candidate into proof of absence.

With **All review states**, saving keeps the current occurrence page and updates
the counters. Fresh per-document counts are also reconciled after occurrence
pagination, so a decision changed elsewhere does not yield a negative counter
when the user next edits it. Other documents retain their displayed review state until
visited or **Refresh reviews** is used; this is not live synchronization across all views.
After a save in a filtered view, the saved result view refills from the first result page
using the **submitted** query, thresholds, scope and review filter. Unsubmitted
form edits are not applied. This also avoids leaving an empty page after its last
matching passage changes state. Saves and pagination callbacks from superseded
search runs cannot modify newer results or their counters.

## Identity and source binding

The existing occurrence ID remains unchanged. It hashes:

- the selected processing-run ID;
- exact/normalized comparison mode;
- textual scorer version and candidate policy;
- the effective comparison query;
- the passage's start/end offsets in Unicode code points.

A review additionally stores revision/source artifact IDs, normalization version
and SHA-256 of the actual matched text. Reads check that stored text/source
provenance still matches the passage. The fingerprint is supplied by search;
the browser does not recalculate offsets or hashes from a displayed snippet.

Consequences:

- Repeated occurrences have independent decisions, as do different documents.
- A different query or comparison mode has independent decisions, even at the
  same source location. Normalized queries differing only by the documented
  normalization rules share their effective-query identity.
- Changing thresholds or enabling/disabling semantic scores preserves a decision
  **if the identical passage is retrieved again**. If another threshold selects
  a different word window, that is a different occurrence.
- Semantic model identity is not part of the human decision: the decision belongs
  to the query and passage, not to a particular model score.
- A new textual scorer/candidate policy changes occurrence identity conservatively.
- Reprocessing publishes a new processing-run ID; a new revision has its own run.
  Old decisions remain stored and are not applied automatically to either.

Keep/Dismiss are dispositions of a passage for a particular expression. They do
not change original bytes, OCR results, extraction warnings, quality status or the
separate literal absence-search semantics. A Keep decision is not a statement of
legal equivalence or a processing-quality override.

## API and concurrency

`POST /api/search/textual` accepts `review_filter`:

| Value | Meaning |
| --- | --- |
| `all` (default) | Every review state |
| `unreviewed` | Not reviewed, including explicit resets |
| `keep` | Keep |
| `dismiss` | Dismiss |
| `later` | Decide later |

The response echoes the filter and includes `review_counts`. Every returned
document group includes its own complete `review_counts`, independent of its
occurrence page and before the review filter. Each occurrence adds
`matched_sha256` and `review: {decision, version, updated_at}`. An occurrence with
no stored decision is represented as `unreviewed`, version `0`, timestamp `null`;
read-only searches never create review records.

`POST /api/reviews` accepts the occurrence identity, document/revision/run/source
IDs, normalization/scorer/candidate-policy versions, submitted query/mode,
start/end offsets, matched SHA-256, target `decision` and `expected_version`.
All identity fields come from the search response. Successful writes return
`{decision, version, updated_at}` after commit.

Without `search_run_id`, the API validates the latest revision, still-selected processing run, comparison
method, bounds, text fingerprint and occurrence identity. It validates an explicit
source span rather than rerunning textual/semantic retrieval for every click.
Document/selected-text row locks serialize a write with source replacement. A
pending newer processing job has not replaced the selected text yet, so the prior
selected run remains reviewable until publication.

For a [saved search run](saved-search-runs.md), the UI includes `search_run_id`.
The API then validates membership, provenance and archived text, allowing reviews
of historical passages after reprocessing without applying them to newer sources.

Writes use optimistic concurrency:

- `expected_version: 0` creates a decision only if no record exists.
- A positive version updates only the matching current version and advances it.
- Resetting stores an explicit `unreviewed` row and advances the version rather
  than deleting it. A stale version-zero view cannot recreate an old decision.
- A changed source/method/span or stale review version returns actionable HTTP 409.
  Invalid input returns 422. These responses do not overwrite a newer decision.

The UI asks users to refresh reviews after a conflict. It does not automatically
retry with an updated version. If a network error obscures a successful commit,
refreshing the saved view reveals the stored state; optimistic concurrency still prevents blind overwrites.
There is no offline write queue or automatic transfer of annotations to new runs.

## Storage and operation

Migration `0003` adds `passage_reviews`. Composite foreign keys bind run and source
to the stored revision, and constraints enforce valid states, positive versions,
SHA-256 shapes and nonempty spans. An index supports per-run/mode reads. Effective
queries use a text column because casefolding can expand a valid 500-character
input. Stored source text is not duplicated; its fingerprint and provenance bind
the decision to the selected span.

`docker compose up --build` applies the additive migration before starting the API.
No new service, external call or dependency is needed. The table stores the latest
decision, version and creation/update timestamps, not a complete event history or
reviewer audit trail. Historical rows for replaced processing runs remain in the
table. Saved runs now expose their historical passages for review; a standalone
review export remains outside the current implementation.
Downgrading to `0002` removes the review table; original documents, processing
records and artifacts remain. Migration upgrade/downgrade was checked only against
the disposable test database; the normal app was upgraded without a downgrade.

## Validation

On 31 October 2026, **181 backend tests** passed against isolated PostgreSQL with
real OCR and the pinned embedding model. Review checks cover persistence and
resets, query/mode/source/position identity, threshold independence, whole-scope
filtering/counts, Unicode offsets and casefold expansion, pending/replaced sources,
concurrent first writes/updates and invalid or stale write payloads.

All **25 Playwright/Chrome scenarios** passed against the built app. Five new
review scenarios cover persistence across reload/pagination and real semantics,
filtered refill with frozen submitted criteria, failed/conflicting writes and real
reprocessing, late successful saves after replacement searches in both All and Not
reviewed views, and counter reconciliation after another view changes a passage.
Only failure presentation uses an isolated mocked 503; successful saves, conflicts,
reprocessing and the delayed saves exercise the actual API/database.

The English desktop and 390px mobile review controls were visually inspected.
TypeScript/Vite, Ruff, Prettier, dependency consistency, local Markdown links,
Alembic metadata check and diff checks passed. Migration `0003` was tested on the
isolated database, including downgrade/upgrade; the running app's existing store
was upgraded normally. No dependency or new service was added.

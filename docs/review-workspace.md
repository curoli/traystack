# Passage review workspace

**Similar passages** now presents a compact list on the left and one selected
passage on the right. Each list entry identifies the document, review state and
both available scores. The detail pane shows context, highlighted matched text,
the query/passage differences and original revision/page references. Source
quality warnings stay visible; technical provenance remains in expandable details.

**Search parameters** can be collapsed without losing unsubmitted edits. Search
history, saved-run controls and exports remain available. On screens up to 850px,
the list sits above the detail pane. The list has its own bounded scroll area;
on desktop it stays alongside the detail view. Review decisions stay accessible
in a sticky action panel while reading context or archived source text.

## Navigation and keyboard

- Choose any entry in **Passage list**, or use **Previous passage** and
  **Next passage**. Navigation crosses documents and the previous result-page
  boundaries; the selected passage's position is announced.
- **Next unreviewed** finds the next Not reviewed occurrence in the current
  review-filtered view, wrapping to its beginning. It excludes the current item
  and is disabled when no other unreviewed passage is available in that view.
- While a list entry is focused, ↑/↓ selects the adjacent entry and Home/End
  selects the first/last. The selected entry is the list's single Tab stop.
  Tab then reaches navigation and native review buttons; Enter/Space activates
  them. There are no global single-letter shortcuts that interfere with typing.
- **Refresh reviews** retains the selected occurrence when it is still in the
  refreshed view. A different run starts with its own first matching occurrence.
- **View source text** opens the preserved extraction inside the selected detail
  pane. Selecting another passage clears that source viewer; repeated source
  opening retains its existing focus behavior.

Saving Keep, Dismiss or Decide later keeps the selection in All review states.
In a filtered view, an occurrence leaving the filter is removed locally and the
next remaining occurrence at that position is selected (or the preceding one at
the end). Focus moves to the detail pane, including when the last item disappears.
Unsubmitted query or threshold edits are never applied by a save or navigation.

## Progress, consistency and errors

**Final decisions** counts Keep + Dismiss over every stored similarity match,
before the review filter. Decide later and Not reviewed remain pending; the
separate state counters explain the remainder. A zero-match run shows zero progress
without treating unsearchable documents as reviewed. Unsearchable documents stay
in their own paginated section outside the positive passage list.

The workspace loads current review decisions once, then applies confirmed writes
to local selection, counters and the current filter. It does not poll other views.
Use Refresh reviews to reconcile external decisions. Optimistic concurrency still
rejects stale writes: errors leave the prior decision and counts intact, and no
blind automatic retry overwrites another reviewer. Navigation is disabled during
a save; a superseded workspace's load/save callback cannot change a newer run.

A failed workspace read displays an explicit error and retry action, without
showing a partial list. Stored method/version mismatches are rejected rather than
mixed into the selected comparison. Existing quality warnings, source validation,
saved snapshots and full CSV/JSON export semantics remain in force.

## Data access

`GET /api/search-runs/{id}/workspace?review_filter=all` returns the complete saved
matches and current review overlay in one read-only REPEATABLE READ transaction.
It uses the same integrity checks and review projection as saved result reads;
no matching, normalization or model evaluation is rerun. `review_filter` accepts
the existing all/unreviewed/keep/dismiss/later values. The original captured scope
remains fixed. Pagination offsets are zero and limits describe the full returned
sets. Ordinary paginated saved-result reads remain available to API consumers.

The existing capture budgets bound this response, including the 2,500 textual
candidate cap and snapshot byte/document limits. There is no new candidate index,
background queue, database migration or external service. For larger review sets,
virtualized list rendering or server navigation can be evaluated separately;
this increment keeps all bounded matches available for direct navigation.

## Validation

216 backend tests passed against isolated PostgreSQL with real Tesseract OCR and
the pinned local embedding model. The new workspace regression loads 28 documents
and 168 occurrences beyond original page limits, verifies current/captured reviews,
full-response offsets/limits, invalid filters and `no-store` headers, and fails if
retrieval runs. Ordinary saved-result pagination remains covered.

All 32 Playwright/Chrome scenarios passed against a fresh isolated Compose app.
The two new workspace scenarios cover cross-document and former page-boundary
navigation, arrow/Home/End and native button keyboard controls, wrapping to the
next unreviewed occurrence, selection retention on refresh, collapsible parameters,
filtered-save focus and progress, source switching and unobscured mobile source
headings with sticky decision controls. Existing review conflict/late-save,
workspace retry/late-read, semantic, historical source, export and workload cases
were adapted to the selected-passage interface and passed.

Desktop and 390px mobile views were visually inspected. TypeScript/Vite, Ruff,
Prettier, dependency consistency, Alembic metadata comparison, local documentation
links and diff checks passed. No migration was added. The normal app received the
final build without deleting its records. The isolated browser app and disposable
backend database were removed after checks.

The accumulated normal test store hit the existing 2,000,000-comparison search
budget in a workload run; final browser validation used a clean synthetic store.
No work/candidate budget was raised. This UI change does not establish full-corpus
search scalability.

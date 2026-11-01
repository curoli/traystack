# Unified document search and match review

The interface has one search workflow. Exact matching is available by setting the
textual minimum to 100 in the chosen Exact/Normalized comparison mode. Semantic
similarity is always computed for new UI searches; its minimum remains editable
from 0 to 100. Zero retains all textual candidates while showing their semantic
scores. Semantic 100 explicitly requires identical comparison text.

The literal search API remains available for diagnostic/integration consumers,
but has no separate interface. The document groups below are decision-based views,
not automatic proof that an equivalent legal clause is missing.

## Categories and scope

A document has one optional editable category. Set **Category (optional)** during
upload, or select a document under **Manage documents**, edit **Category** and
choose **Save category**. Clearing it makes the document uncategorized. Category
changes do not change bytes, extraction or existing decisions.

**Document category** selects all documents, uncategorized documents, or one exact
category. Category matching is case-sensitive. The server applies this selection
before retrieval, resource budgets and snapshot capture. Ready-only eligibility
still applies. Existing saved searches retain their captured category/scope even
if document categories subsequently change. Run again evaluates the original
criteria against the current collection.

There is no “open document” search switch. Review state is a property of passages,
so the search form no longer contains a Review status selector.

## Three passage states

Each passage has three state buttons, with exactly one selected:

- **Confirm match**: explicitly retain the passage as a match.
- **Dismiss match**: explicitly reject the passage as a match.
- **Unreviewed**: leave/reset the passage pending.

Initially a passage is Unreviewed unless automatically confirmed or carrying an
existing explicit decision. Choosing a state does not move the selection. Saved
versions still protect against overwrites; failures retain the prior state.
Internally, compatible API values remain `keep`, `dismiss` and `unreviewed`.
Legacy `later` records remain stored and appear as Unreviewed in the workspace.
The UI export passes `three_state=true` to apply the same interpretation, including
Unreviewed filtering, while retaining original capture-time evidence separately.
Diagnostic API defaults retain their legacy representation.

## Automatic confirmation

**Auto-confirm strong matches** is enabled by default, with separate textual and
semantic minima of **100 / 100**. Both scores must reach their auto-confirmation
thresholds after passing retrieval thresholds. Disable the option for fully manual
review, or choose other auto-confirmation minima deliberately. Similarity scores
are not probabilities or legal-equivalence guarantees.

The policy is stored in the immutable search request. New snapshots retain
unrounded textual/semantic scores so policy boundaries never depend on displayed
rounding. Auto-confirmation is a deterministic projection for that saved search,
not an unconditional write over shared human annotations. It applies only where
no explicit decision record exists (version zero). Explicit confirmation,
dismissal or reset to Unreviewed always takes precedence, even on exact matches.
A manual reset persists across refresh, reload and searches using more permissive
policies. Merely reading a search never creates decision rows.

Automatically confirmed passages are counted but hidden from the passage list by
default. **Show automatically confirmed passages for review** reveals them. Manual
confirmed/dismissed passages remain visible; this switch hides automatic decisions,
not all confirmed passages. A state change converts an automatic result to an
explicit decision and keeps the passage selected. A list containing only automatic
matches shows an explanatory message rather than claiming no candidates exist.

Capture-time review state is retained separately from current review state.
Historical runs without semantic scores do not invent auto-confirmation; rerunning
through the new UI computes semantic scores.

## Navigation

**Previous unreviewed**, **Previous**, **Next**, **Next unreviewed** move to another
document's candidate passage without writing a decision. Unreviewed navigation
skips documents without an eligible pending passage in that direction. It does
not wrap. Buttons disable at boundaries and during saves. Multiple passages within
one document can be selected directly from the list using mouse or arrow/Home/End
keys. The selected list item remains the single Tab stop.

## Three document groups

Below the passage list, three collapsed groups initially show document counts:

1. Documents with at least one confirmed match.
2. Documents with no confirmed match but at least one unreviewed match.
3. Documents with no confirmed or unreviewed match.

These groups partition the complete captured **searchable document scope**, not
just documents with visible candidates. Confirmation takes precedence over pending
passages. Group 3 contains both documents with only dismissed candidates and
those with no candidate passing the retrieval thresholds. Ineligible documents
are excluded from all groups; they are not disguised as negative findings.

Counts include automatic confirmations and remain independent of whether those
passages are shown. Confirm/reset/dismiss updates groups immediately after a
successful save. Expanding a group renders its document list, with batches of 100
and Show more documents where needed. Choosing a document with candidates selects
its passage; choosing one without candidates shows that document's empty detail
view instead of leaving an unrelated passage displayed. Original downloads remain
available for inspection. Group 3 alone does not establish literal or legal absence.

## Storage and API

No migration is required: category uses document JSON metadata, the auto-confirm
policy and raw scores use existing snapshot JSON, and shared manual decisions keep
the existing optimistic-concurrency table.

- `GET /api/categories`: current category choices.
- `PATCH /api/documents/{id}/category`: `{category: "Supply"}` or null to clear.
- Upload accepts an optional `category` form field.
- Textual requests accept `category`, `uncategorized`, paired nullable
  `auto_confirm_textual` / `auto_confirm_semantic`. Auto-confirm requires semantic
  scoring. Legacy API defaults do not enable it implicitly. Auto-confirm policy is
  applied to saved runs; the ephemeral textual endpoint explicitly rejects it.
- Saved responses/workspace expose `document_outcomes`, policy fields,
  `auto_confirmed` and preserved `raw_textual_score` / `raw_semantic_score` values.
- CSV retains category/policy, automatic/manual provenance and unrounded scores;
  JSON also contains the complete document outcomes. Original files remain separate.

All readiness, checksum, bounded retrieval, model failure and immutable-source
rules continue to apply. Document preparation stays under Manage documents.

## Validation

Validated with 226 backend tests (including PostgreSQL, real OCR and local
embeddings) and all 32 browser scenarios. TypeScript, the production frontend
build, Ruff, Prettier, local documentation links and Git whitespace checks pass.
Desktop and mobile layouts were inspected. The normal Docker Compose app was
rebuilt and started successfully; no schema migration is needed and original
documents are preserved.

# TrayStack — presentation guide (18 minutes)

Original core-demo outline dated 30 October 2026, translated into English.
Upload, extraction, quality, literal search and evidence are demonstrated locally.
Azure, SharePoint and the pilot are proposals. Real historical handwriting has not
been evaluated. Later textual/semantic search, saved reviews/runs and exports are
now implemented; see the [user guide](user-guide.md) for current functionality.

## 1. Problem and success criterion · 0:00–1:30

**Slide:** “Find contracts faster, with traceable evidence and visible uncertainty.”

- Find a company name and identify contracts whose extracted text lacks a phrase.
- Current work means opening, searching and checking documents individually.
- Batch the search work while Legal retains the actual decision.

**Talk track:** “The critical case is the missing passage. A failed match can also
mean we could not read the scan. TrayStack therefore distinguishes found, not
found in processed text, and unverifiable.”

## 2. Wording, quality and provenance · 1:30–3:00

**Slide:** Did the job finish? Were all pages processed? Are quality issues known?

Exact checks wording; Normalized standardizes Unicode, case and whitespace while
preserving numbers, negation and punctuation. Both examine the entire selected text
of the latest revision. Positives can carry warnings; negatives require complete
coverage without known issues. Neither guarantees perfect OCR.

A top-ten list of similar paragraphs cannot prove absence elsewhere in a contract.
Legal equivalence requires separate evaluation; an LLM is unnecessary for this
literal workflow. Current optional semantic scores do not change that contract.

## 3. Live demo · 3:00–9:00

Use the [demo setup/fallback](demo.md), with four synthetic files processed in
advance. Install OCR before presenting; do not use real contracts.

| Time | Action | Point to demonstrate |
| --- | --- | --- |
| 3:00–4:00 | Upload A, download original, start processing | Document/revision/artifact differ; original bytes remain unchanged |
| 4:00–5:00 | Open page text, JSON/Markdown and job history | Real processing with source, parameters and versions |
| 5:00–6:15 | Normalized search for `The receiving party shall not disclose confidential information` | A and printed scan P match; open evidence and original |
| 6:15–7:30 | Switch to Not found in extracted text | D is negative; difficult flagged E remains unverifiable |
| 7:30–8:15 | Inspect E's quality/review group | Complete coverage can still require review; degraded print is not handwriting evaluation |
| 8:15–9:00 | Explain reprocessing/provenance | New jobs create new artifacts; failures retain old selected text and expose errors |

**Talk track:** “A company name uses the same literal workflow. I inspect the
passage and original; changes to the contract follow the approved legal process.
The application does not modify contract files.”

## 4. Implementation and proposed Azure operation · 9:00–11:00

**Slide:** [Production diagram](production.md).

Local components: React/TypeScript, FastAPI, separate Python worker, PostgreSQL and
file volume. Jobs are claimed transactionally; publication changes selected text.
Search snapshots keep results, provenance and page evidence consistent.

Proposed Azure mapping: Container Apps for web/API/worker, Azure Database for
PostgreSQL, Blob Storage, Entra ID, Managed Identities and monitoring. None is a
claim of deployed resources; blob adapter and authorization remain missing.

SharePoint stays authoritative. Import must preserve source/version, permissions
and deletion semantics. The restricted archive REST API receives only an extra
copy; it is not a search/extraction backend.

## 5. Microsoft comparison and selection · 11:00–13:00

**Slide:** [Comparison table](production.md).

- Local extraction is a reproducible offline baseline. Printed scans are checked;
  Tesseract is not presented as reliable handwriting recognition.
- Azure Document Intelligence Read is a documented print/handwriting candidate
  with positional data; performance on historical contracts remains unmeasured.
- SharePoint OCR plus existing search deserves evaluation. OCR/indexing alone do
  not establish complete negative-search semantics with quality exclusions.

**Decision:** evaluate existing Microsoft capabilities on the same approved corpus
before rolling out a custom system. Keep custom components where quality,
traceability or workflow justifies them. Do not claim better recognition, lower
cost or time savings without measurement.

## 6. Pilot and adoption · 13:00–16:00

**Slide:** “Define together → compare under controlled conditions → expand selectively.”

Proposal: a Legal owner, three to five users, Engineering and an information-security
contact. Agree size/duration beforehand; this is not an existing organizational decision.

1. Select two real tasks and distinguish wording from meaning.
2. Build an approved, human-checked reference set stratified by digital PDF, print
   and difficult/handwritten pages; separate known positives, negatives and undecidable cases.
3. Teach evidence/original inspection, warnings and escalation of unverifiable cases.
   The prototype has no quality-review approval action.
4. Counterbalance manual/assisted task order to avoid memory bias in time measurement.
5. Review error types/terminology weekly with Legal. A business owner prioritizes;
   Engineering owns processing failures and operation.

| Metric | Definition / decision |
| --- | --- |
| Positive precision/recall | Correct document-passage pairs / proposed or known positive pairs; unverifiable known positives count as missed for recall |
| False absence | Negative suggestions despite known presence / all negative suggestions; also report absolute counts by document type |
| Review work | Unverifiable fraction and original-inspection minutes, included rather than excluded as failures |
| Time to decision | Median and slow cases, including manual follow-up, compared with manual baseline |
| Usability | Task completion, misunderstanding of the three statuses and concrete feedback |

Agree tolerated error and minimum benefit before evaluation. Investigate any false
absence suggestion; until resolved, require original inspection for that pilot
workflow. Inadequate handwriting remains manual. Roll out only after business
acceptance and operational prerequisites.

## 7. Limits, next steps and discussion · 16:00–18:00

**Slide:** “Core demonstrated; production readiness and real handwriting remain open.”

- Full scans do not establish large-collection performance; later bounded
  [measurements](search-performance.md) are not full-corpus load tests.
- Heuristics miss some OCR errors; historical handwriting needs a reference set
  and potentially another extractor.
- Authentication, permission inheritance, retention, restore and full audit remain
  production requirements, not delivered infrastructure.
- At the original milestone, fuzzy/semantic search and revision UI were deferred.
  Textual/semantic comparison is now implemented; convenient revision creation and
  additional uploaded representations remain future work.

**Closing question:** “Which contract types and errors cause the most review work
now? That is where I would focus the reference corpus and pilot.”

## Prepare for questions

- **Why no agent?** Bounded wording search needs no autonomous tool selection;
  an agent would not guarantee complete negative findings.
- **Why PostgreSQL?** One consistent metadata/job/text store serves this bounded
  prototype. Larger collections require measurement and optimization.
- **Is a hash compliance evidence?** It checks byte identity, not retention,
  authorization or a legally compliant archive.
- **What happens after a crash?** Published results remain; interrupted running
  jobs require documented operator recovery.
- **How was AI used?** Codex assisted implementation/documentation, checked by real
  API/OCR/browser tests and PR reviews. Runtime uses no generative AI/cloud models;
  optional embeddings run locally.

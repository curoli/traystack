# Engineering decisions

- **Completed local core:** milestone 4 added executable demo checks and an
  introduction/presentation plan. Azure, SharePoint, real-handwriting evaluation
  and the user pilot remain proposals. The [production design](production.md)
  compares Microsoft alternatives without adding runtime cloud/LLM/search services.
- **Small first vertical slice:** combined upload creates a document, revision 1
  and original. Further revisions/representations fit the model; convenient write
  APIs and management UI remain future work.
- **PostgreSQL from the start:** JSONB, foreign keys and migrations are tested on
  PostgreSQL. Initial fuzzy retrieval scans bounded full text with RapidFuzz;
  `pg_trgm` and persisted segments require measured justification.
- **Originals and provenance:** sanitized filenames are display fields, never
  storage paths. SHA-256 addresses contents; artifact IDs identify provenance.
  Equal upload bytes do not imply the same logical contract.
- **Local storage:** API runs without root; a named volume stores originals. The
  stream/byte storage interface permits a future blob adapter, not yet implemented.
- **Honest status:** upload is not extraction. Job, coverage and quality remain
  separate. Review flags survive complete extraction and later runs of the same
  source; they are not automatically cleared or treated as quality approval.
- **Local API documentation:** packaged Swagger assets replace CDN dependencies;
  the core requires no external services after build.
- **Search contract:** exact/normalized examine all selected text. Missing or
  questionable extraction is unverifiable; positives have source evidence.
  Textual and semantic similarity retrieve positive candidates, never prove absence.
- **One job is one run:** one active job per revision, claimed transactionally.
  Retry creates another record. Old artifacts remain; only completed publication
  changes selected text.
- **Simple queue:** PostgreSQL is sufficient for the local prototype. A separate
  worker keeps OCR outside HTTP. Hard crashes require explicit recovery rather
  than unsafe timed takeover while a predecessor may still be running.
- **Conservative extraction:** whole PDF pages containing raster images use OCR,
  even with embedded text, avoiding unread scans hidden by headers. Combining
  high-quality mixed-layout regions may be future work. Empty pages require review.
- **Quality heuristic v1:** fewer than ten alphanumeric characters, replacement
  characters, or more than max(5, 8% of characters) unusual characters flag review.
  OCR flags a mean word score below 80/100 or over 20% of words below 50/100;
  missing confidence also flags review. These are not calibrated probabilities or
  handwriting/wording guarantees.
- **Stable normalization:** NFC, whitespace and casefold retain legally meaningful
  characters; ambiguous hyphenation is not repaired. Casefold can expand characters,
  so page offsets explicitly refer to normalized text, not guessed raw positions.
- **One search snapshot:** latest revision is chosen regardless of processing.
  PostgreSQL `strpos` and read-only REPEATABLE READ keep counts, snippets, provenance
  and page references consistent. Unverifiable documents have separate pagination.
- **First literal occurrence per document:** results count documents rather than
  ranked segments. Offsets specify raw/normalized Unicode code points. Changed
  selected text asks users to rerun rather than attaching evidence to new content.
- **Control before semantics:** textual zero is rejected. Shared query assessment
  illustrates length-dependent edit budgets and risk without claiming a safe
  learned threshold. Occurrence/density/compute limits abort without successful
  subsets. The UI never raises thresholds silently and can narrow to one document.
- **Semantics after concrete passages:** pinned local MiniLM ONNX embeds retrieved
  passages on demand and caches by text/pipeline. Context is displayed but not
  embedded. Filtering precedes counts/pagination and keeps textual ranking.
  Semantic 100 explicitly requires identity; lower scores are not legal confidence.
  Overlong input is rejected, not truncated. Fixed singleton inputs avoid dynamic
  INT8 dependence on batch/cache state. See [semantic rules](semantic-search.md).
- **Decisions per expression and occurrence:** Keep/Dismiss/Later are distinct from
  Not reviewed. Identity uses job, mode, effective query and occurrence policy;
  thresholds/model are not human-decision identity. Resets retain versions to block
  stale writes. Counts precede review filtering; new processing IDs get new
  occurrences. Decisions are shared, without accounts or complete event audit.
- **Measured optimization with unchanged results:** a bounded mixed collection
  separates matching, model startup, new embeddings, cache hits and HTTP time.
  Prepared word positions and conservative length pruning reduce Python work;
  complete cache hits avoid directory scans. Compare scores/occurrences/budget
  usage against baseline. [Measurements](search-performance.md) do not evaluate
  the full original corpus or establish recall of a new candidate index.
- **Durable full result snapshots:** saved parameters alone cannot reproduce old
  results after reprocessing/library changes. Successful UI runs save all matches
  after both similarity filters, before review filtering/pagination, with scope and
  deduplicated per-job source text. Reopen without matching/models; Run again creates
  a linked new snapshot. Current reviews stay editable and capture-time state is
  retained. Atomic writes and explicit caps prevent partial saves. See
  [saved searches](saved-search-runs.md).

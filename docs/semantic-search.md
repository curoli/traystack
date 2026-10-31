# Semantic comparison of textual candidates

**Similar passages** optionally compares each retrieved passage with the search
expression using local embeddings. Enable **Compare meaning with local embeddings**
and set **Minimum semantic match**. Textual search remains the first stage; a
semantically related expression that fails the textual threshold is not retrieved.
The existing **Literal search** absence workflow is unchanged.

## Score contract

Both thresholds must pass. Textual similarity still uses the
[documented character-edit score and candidate rules](textual-search.md).
The semantic score has a separate, versioned contract:

- `null` / omitted `minimum_semantic_score`: embeddings are switched off.
- `0`: compute and display scores, retaining every textual candidate.
- Values between 0 and 100: filter on the unrounded semantic score.
- `100`: retain only identical comparison text. This is an explicit product rule,
  not a claim that a cosine of one guarantees equivalent meaning.

For nonidentical comparison text, the score is
`min(99.99, 100 * max(0, cosine))`. Identity yields 100 explicitly. The comparison
texts are the effective query and matched passage in the selected mode: normalized
mode uses normalized text; exact mode keeps case and whitespace. The raw cosine
is also returned. Negative cosines map to zero, so semantic zero truly disables
filtering. Scores are returned to four decimals and shown to two decimals;
filtering uses the original value. A nonidentical passage cannot round to 100.

These scores are **not probabilities, calibrated confidence, legal equivalence or
proof of absence**. The same topic can contain a changed negation, name, amount or
deadline. The UI displays context and textual differences for human inspection.
A threshold below 50 gets a permissiveness warning; semantic 100 combined with a
textual threshold below 100 gets an exact-only explanation. These are usability
rules, not empirically validated safe thresholds.

## Pipeline and provenance

1. Select the same document/revision/processing-run snapshot as textual search.
2. Find and consolidate textual candidates with the existing budgets. No new
   candidates or alternative overlapping windows are introduced by embeddings.
3. Embed the effective query and each complete matched passage. Context shown
   around the passage is **not** included in its embedding.
4. Apply the semantic threshold before document/occurrence counts and pagination.
5. Keep the existing textual ranking. The semantic score acts as a second filter,
   not an additional retrieval index or automatic reranking policy.

Every result has its textual `score`, nullable `semantic_score` and
`semantic_cosine`, source offsets, context, differences and processing provenance.
The response echoes `minimum_semantic_score`, reports `textual_candidates_total`
before semantic filtering and includes model/pipeline/score version metadata.
Summary counts and result totals describe passages passing both filters.
Unsearchable documents retain their separate group. No match is proof of absence.
Submitted semantic settings survive document and occurrence pagination; changing
form inputs does not change an existing search. Abort callbacks remain bound to
their originating search request ID. Occurrence pagination refuses to mix a
changed semantic pipeline or textual scoring method into an existing result card.

The model is
[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
using the [Xenova quantized ONNX conversion](https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/tree/2c4055b12046f11709e9df2c122e59ffbdc2f900).
It produces 384-dimensional embeddings with attention-mask mean pooling and L2
normalization. CPU ONNX Runtime uses two inference threads and one inter-op thread;
telemetry is disabled. The full input limit is 128 model tokens, including special
tokens. Truncation is explicitly disabled: an overlong query **or any candidate**
fails the complete request with an actionable 422 instead of silently discarding
text. This matters for long words and OCR noise as well as long expressions.

Artifacts are pinned to revision `2c4055b12046f11709e9df2c122e59ffbdc2f900` and
verified against SHA-256 constants in
[semantic_model.py](../backend/traystack/semantic_model.py). The response/cache
pipeline identity includes the artifact revision, pooling/tokenization policy and
ONNX Runtime / Tokenizers versions. Fixed-length singleton inference avoids
batch-dependent dynamic INT8 quantization: adding another candidate or hitting a
cache entry must not change an existing text's vector. This is exercised using the
actual model, including partial cache regeneration.

## Offline setup and cache

`docker compose up --build` downloads model weights (about 118 MB) and tokenizer
(about 17 MB) during the backend **build**, verifies their hashes and includes
Apache-2.0 license and attribution files. No API key is needed. Search requests
load local files only; there is no automatic runtime download or cloud fallback.
Model initialization is lazy, so a missing model does not disable textual search.
An unavailable model or busy inference engine returns 503 for semantic requests.

For native development and real-model tests:

```sh
.venv/bin/python -m traystack.prepare_semantic_model data/models/minilm
SEMANTIC_MODEL_PATH=data/models/minilm STORAGE_PATH=data/blobs .venv/bin/uvicorn traystack.main:app
```

The default Docker model directory is `/opt/traystack/semantic-model`.
`SEMANTIC_MODEL_PATH` overrides it for native development. The derived embedding
cache lives under `STORAGE_PATH/embedding-cache`; keys include pipeline identity
and SHA-256 of the complete comparison text. Original contract bytes and
processing artifacts are not modified. Files are written atomically, validated on
read, and corrupt entries are regenerated. Each pipeline cache holds at most
10,000 entries per process; a full cache permits inference without new writes.
The current deployment uses one API process. Multiple independent API processes
would need coordinated cache quota enforcement. Old pipeline directories remain
until explicitly removed; there is no automatic eviction across model versions.
Cache removal causes recomputation and must not include original artifact files.

Only actual query/candidate texts are embedded on demand. Repeated or identical
texts reuse their vectors. Reprocessing needs no speculative embedding index:
changed text gets a different cache key; source provenance still identifies its
specific processing run.

## Bounded work and failures

Existing textual budgets apply first. Semantic requests additionally allow at
most 500 retained textual candidates (before deduplication), 40,000 tokens across
unique query/candidate texts, and a 20-second cooperative comparison budget.
The deadline is checked between inference calls and before returning, including
warm-cache requests. One inference call cannot be interrupted mid-call; model
initialization is outside this comparison deadline. At most one comparison per
engine runs at a time; another gets a retryable 503 rather than waiting in a queue.
These prototype workload limits are not calibrated quality thresholds.

Candidate/token/time overflow uses the existing structured 422 abort response:
`results_complete: false`, reason, resource, limit and observations. There is no
partial result list, success total, silent threshold adjustment or textual-only
fallback. Incomplete work may populate reusable cache entries without publishing
a successful search response. Ordinary model/input failures likewise return no
result snapshot. No background semantic job or manual cancellation API is added.

## Diagnostics and validation

[Ten synthetic diagnostic pairs](../examples/semantic/diagnostic-pairs.json) cover
English/German paraphrases, identity, negations, changed names, amounts, deadlines
and unrelated text. They compare complete pairs; they do not independently assert
that candidate retrieval finds every pair. They are not held-out evaluation,
legal-equivalence labels or a universal threshold recommendation.
For example, changing EUR 500 to EUR 5000 retains about 89.41 semantic points in
this run. The diagnostic values make these model limitations visible.

Reproduce with the pinned model and locked dependencies:

```sh
.venv/bin/python scripts/evaluate_semantic_search.py --model data/models/minilm --output examples/semantic/diagnostic-pairs.json
SEMANTIC_MODEL_PATH=data/models/minilm TEST_DATABASE_URL=postgresql+psycopg://traystack:traystack_test@127.0.0.1:55432/traystack_test .venv/bin/pytest backend/tests -q
```

Without `SEMANTIC_MODEL_PATH`, real-model tests explicitly skip; they never
substitute fake embeddings. Deterministic score/filter contract tests also use
controlled scores to check totals and pagination independently of model quality.
Browser success scenarios use the actual local model. An isolated 503 scenario
checks error presentation. A separate container inference check runs with Docker
networking completely disabled.

On 31 October 2026, all **171 backend tests** passed with isolated PostgreSQL,
real OCR and the pinned embedding model. All **20 Playwright/Chrome scenarios**
passed, including actual semantic scores, zero/100 filtering, frozen pagination
thresholds, changed-method rejection, validation errors, unavailable-model
presentation and the existing delayed-abort regression. The English desktop and
390px mobile layouts were inspected with real synthetic results. TypeScript/Vite,
Ruff, Prettier, dependency consistency, local Markdown links, Alembic schema check
and diff checks passed. Real inference also succeeded in the built container with
`--network none`. No database migration or external runtime service was added.

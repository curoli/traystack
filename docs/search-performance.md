# Search workload evaluation and measured optimizations

This increment checks the working search/review workflow on bounded mixed contract
inputs and makes two measured changes: a cheaper textual window loop and avoiding
a cache-directory scan on complete embedding-cache hits. No scorer, threshold,
candidate policy, search budget, occurrence identity, model or vector format changes.

## Reproducible inputs and privacy

`generate_search_corpus.py` independently authors English/German synthetic supply
agreements with background sections and four query families. Cases include literal
wording, paraphrases, changed negations, amounts, names, deadlines, typed OCR-like
errors and unrelated wording. No private contract sentences are copied.
The [eight-document sample](../examples/search-evaluation/corpus-sample.json) is
checked in with source hashes and normalized target offsets. The generator creates
larger workloads deterministically; its default is 64 contracts with 18 background
sections each. Diagnostic target overlap means that a candidate covers at least
half the authored normalized target; it is not an exact-boundary or legal-equivalence
recall metric. The smaller checked-in sample has three background sections.

The mixed in-process measurement used **16 and 64 authored contracts**, each plus:

- Eight local sources: smallest and median eligible file per root/content type
  from `examples/contracts` and `examples/contract-nli` (four TXT, two HTML, two PDF).
- Two existing synthetic JPEG fixtures, processed by real Tesseract. The difficult
  fixture produced unavailable text and was not counted as a negative match.

Selection inspects PDFs and excludes encrypted files or files above eight pages;
all types have a 1,000,000-byte input limit. At most two roots and two files per
root/type are selected. Eligibility/skipped counts are in the report. These are
bounded samples, not a run over all 759 original files. Extraction used the actual
processing functions, an eight-page limit, 200dpi OCR, 25 million pixels and a
10-second OCR timeout. Local sources were explicitly flagged for manual review;
quality flags are not measured legal/extraction accuracy labels.

The selected ten source files produced nine complete documents and one unavailable
JPEG, with 13 total pages: four plain-text, four embedded-PDF-text, three OCR and
two HTML pages. The mixed profiles contain 26/74 documents, 25/73 searchable texts,
and 532,905/715,887 normalized characters respectively.

Original files are read only. Paths, individual source hashes and detailed source
metadata remain under ignored `data/performance/source-manifest.json`. The
[aggregate report](../examples/search-evaluation/performance-report.json) contains
no private filenames, excerpts or matched passages. Directory names do not verify
original dataset provenance or redistribution permission.

## Textual measurement

The reference is merged PR #11, Git revision `45d49f3`. The benchmark loads that
trusted local revision explicitly and runs reference/current matching code against
identical normalized inputs with the same installed RapidFuzz runtime. It uses
five alternating-order repetitions per query/profile. All passage offsets, full
scores, result order, abort outcomes and remaining work budgets must match exactly;
divergence fails the run. The report records implementation hashes, environment,
corpus digest and every timing sample. No database or HTTP work is included here.

For the larger mixed profile (median of five runs at textual threshold 85):

| Query | Previous text stage | Optimized text stage | Time reduction |
| --- | ---: | ---: | ---: |
| confidentiality | 1178.4 ms | 933.0 ms | 20.8% |
| amount | 966.5 ms | 730.7 ms | 24.4% |
| name | 659.9 ms | 486.3 ms | 26.3% |
| german | 646.6 ms | 452.6 ms | 30.0% |
| common_confidentiality | 675.0 ms | 481.7 ms | 28.6% |

These are single-machine observations, not an SLA, statistical significance claim
or a promise for every threshold or collection size. The first profile likewise
improved. The optimization precomputes word offsets and query length, rejects
clearly impossible lengths before allocating substrings, and retains the original
boundary calculation and full-precision scorer for possible matches. Conservative
integer bounds include padding for floating-point boundaries. Every potential
window is still charged to the existing budget, even if cheaply rejected.

Regression checks compare 1,524 seeded text/query/threshold/budget combinations
against a frozen pre-change matcher, including Unicode, long words, overlaps,
threshold boundaries, subnormal positive thresholds and work/passage aborts.
Scorer/candidate-policy versions and saved review identities remain unchanged.

## Model initialization, cold embeddings and warm embeddings

The benchmark separately times model construction, comparison with an empty vector
cache, actual ONNX inference time/call count and five warm-cache comparisons.
Reference/current engines use the same pinned model and installed runtimes; cold
and warm vectors/scores must be exactly identical. All warm comparisons must make
zero inference calls. Cold means a new engine/vector-cache instance, **not** a
flushed OS file cache. Initialization and cold comparison are single observations
per case; warm timings have five repetitions.

The directory-size experiment has **10,000 entries**, including genuine embeddings
for the query/candidates and inert placeholder files. Placeholders only simulate
directory traversal cost; they are not 10,000 generated/validated embedding vectors
and are never read as vectors. The reports give their exact counts.

In the 64-document profile, warm comparison medians fell from about **14–15 ms**
to **0.2–0.9 ms**. This is a stage-level directory experiment, not an equivalent
speedup for an entire search. Tokenization, cache validation and scoring still run.
A missing/corrupt vector still triggers quota counting and inference; complete hits
need neither new cache writes nor a scan of all existing entries. The model,
normalization and cache keys are unchanged.

## Actual HTTP/database workflow

A separate empty Docker Compose project uploaded and processed **32 generated
contracts and both JPEG fixtures** through the actual API/worker, verified original
hashes and then issued five textual requests, one first semantic request and five
warm semantic requests per query. The normal app database was not reused. The
[HTTP report](../examples/search-evaluation/api-report.json) includes database,
serialization and local HTTP overhead; it has a different, smaller dataset from
the in-process mixed benchmark and makes no before/after HTTP speedup claim.

| Query | Textual HTTP median | First semantic request | Warm semantic HTTP median |
| --- | ---: | ---: | ---: |
| confidentiality | 188.4 ms | 1007.0 ms | 189.8 ms |
| amount | 133.5 ms | 214.3 ms | 142.2 ms |
| name | 106.0 ms | 144.2 ms | 108.3 ms |
| german | 104.5 ms | 169.4 ms | 103.3 ms |

Only the first family's first semantic request includes lazy model initialization;
later families use the loaded model but previously uncomputed query/candidate
vectors. Upload/processing finished before timing searches. The tool subsequently
checked source text, Keep → Dismiss → Decide later → Not reviewed persistence,
material differences for negation/amount/name and retrieval of the actual printed
OCR clause. Failed assertions or processing jobs do not produce a new success report.

## Browser improvements and verification

Completed search requests display elapsed time, measured in the browser through
response decoding (not React paint or document processing). A document card now
shows **Loading passages …** and `aria-busy` while occurrence pagination is pending.
The duration is updated only by the current search request; no estimate is shown
as a completed result. Existing stale-request guards remain intact.

All **187 backend tests** passed with isolated PostgreSQL, real OCR and the actual
pinned model. All **26 Playwright/Chrome scenarios** passed. The additional browser
workflow uploads/processes 32 synthetic contracts, searches across document pages,
opens the source, checks negation/amount/name/German differences, saves/revisits
reviews, and checks mobile width. The delayed-pagination regression also verifies
the loading indicator. The 32-contract case also passed twice in succession with
unrelated random batch identifiers against an accumulating store. Use a dedicated
stack for controlled workload sizes. TypeScript/Vite, Ruff, Prettier, schema/dependency checks and
local Markdown links passed. No dependency, service requirement or migration was
added to the app.

## Reproduce

From the repository root with locked dependencies, real Tesseract and the prepared
pinned model:

```sh
.venv/bin/python scripts/generate_search_corpus.py --output data/performance/synthetic-corpus.json
.venv/bin/python -m scripts.benchmark_search --reference-ref 45d49f3 --model data/models/minilm --sources examples/contracts examples/contract-nli --cache-entries 10000 --repeats 5 --output data/performance/report.json
```

The reference commit must exist locally; shallow clones may need its history.
The reference option executes trusted repository code, never source-document text.
Omit `--sources` for a synthetic/OCR-only run. Reports explicitly distinguish
complete searches from aborts and discard partial result lists.

For the real HTTP run, choose a **new, disposable project name** and unused ports:

```sh
WEB_PORT=18080 API_PORT=18000 docker compose -p traystack-search-evaluation up -d --build --wait
.venv/bin/python -m scripts.evaluate_search_api --base-url http://localhost:18080 --count 32 --output data/performance/api-report.json
WEB_PORT=18080 API_PORT=18000 docker compose -p traystack-search-evaluation down -v
```

The API tool requires an empty store, refuses external hosts and creates synthetic
records; its final command removes only that disposable project's volumes. Do not
substitute the normal project's name. The in-process tool imports no app records
and modifies none of the local source files.

The next scaling decision should be based on larger measured collections and
recall checks for a candidate index. These bounded results do not establish that
full-corpus fuzzy searches fit the existing budgets, and do not calibrate safe
semantic or legal-equivalence thresholds. Materially changed amounts still score
around 90 here, so human comparison remains essential.

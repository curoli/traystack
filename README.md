# TrayStack

**Getting started:** The [user guide](docs/user-guide.md) explains startup,
components, uploads, file processing, contains/absence searches, passage review,
saved searches and export using the interface's English labels.

TrayStack is a local prototype for traceable contract storage and full-text search.
**Milestones 1–4 are implemented:** upload PDF/JPEG/PNG and UTF-8 TXT/HTML, download
unchanged originals and process documents in a separate worker. Page text,
structured JSON and Markdown retain source/method provenance. Job status, coverage
and quality are separate. Exact/normalized search returns evidence, negative
findings over fully processed text and a separate unverifiable group.

The interface and documentation are English. Dates use English month names and
24-hour time in the browser's timezone. Uploaded document contents, titles,
metadata and multilingual evaluation examples retain their original language.

**Similar passages** adds textual similarity, context and highlighted differences.
An optional local semantic stage compares only the textually retrieved passages.
Scores are not legal confidence or equivalence. Expression-specific guidance and
runtime budgets constrain broad queries; textual zero is not allowed.
**Search only the open document** narrows scope.

**Keep / Dismiss / Decide later** saves decisions per occurrence. Not reviewed is
separate; Reset review restores it. Successful Similar passages searches save
complete matches, scores, captured scope and historical text. Saved searches reopen
without retrieval; Run again creates a separate linked run. CSV/JSON exports cover
all selected results, with independent review filtering. The review workspace
combines a compact list with one selected detail pane, cross-document navigation,
keyboard controls and final-decision progress.

Technical contracts and evidence:

- [Literal search](docs/search.md), [textual matching](docs/textual-search.md),
  [semantic comparison](docs/semantic-search.md).
- [Reviews](docs/passage-reviews.md), [workspace](docs/review-workspace.md),
  [saved runs](docs/saved-search-runs.md), [exports](docs/search-exports.md).
- [Data and OCR evaluation](docs/data-evaluation.md): local import tools and 300
  reproducible handwriting simulations with ground truth; [three samples](examples/synthetic-handwriting/samples/manifest.json)
  are included, and the full image corpus is generated locally.
- [Mixed workload/performance report](docs/search-performance.md): bounded
  real-source, synthetic, OCR and embedding-cache measurements.
- [18-minute presentation](docs/presentation.md) and [production proposal](docs/production.md).

## Start

Requires Docker with Compose v2+ and access to the Docker daemon. The first build
downloads images, dependencies and the pinned local model/tokenizer (about 135 MB).
The running app needs no cloud services, API keys or external network calls;
API documentation assets are also served locally.

```sh
docker compose up --build
```

- Interface: <http://localhost:8080>
- API documentation: <http://localhost:8080/docs> or <http://localhost:8000/docs>
- Readiness: <http://localhost:8000/api/health>

PostgreSQL, migrations, API, worker and web server start in dependency order.
The migration job normally exits with code 0. Data/originals live in named Docker
volumes; `docker compose down` stops the stack and retains volumes.

Defaults work without `.env`. Copy `.env.example` to `.env` for customization,
including `WEB_PORT`, `API_PORT` and `UPLOAD_MAX_BYTES`. Nginx separately limits the
whole request to 26 MiB; increasing upload limits also requires adjusting
`frontend/nginx.conf`. Database ports are not exposed to the host; API/web bind to
loopback. Default credentials are for the local demo only.

## Five-minute demo

1. Open the interface, enter a title and upload
   `examples/synthetic-contracts/A-confidentiality.pdf`.
2. Inspect document/revision/artifact IDs, MIME type, size and SHA-256.
3. Download the original and compare its bytes.
4. Choose Start processing, watch status, inspect coverage/quality separately,
   then open View page text and preview/download JSON and Markdown.
5. Process `D-delivery.pdf` (no target phrase) and `P-printed-scan.jpg` (real OCR).
6. Upload `E-difficult-scan.jpg` with Manual review required. The flag persists
   after processing and cannot be cleared merely by another OCR run.
7. Reprocess A: new artifacts are published and selected; old artifacts remain.
   Failed runs can be retried as new runs and retain previously selected text.
8. Under Literal search, enter the confidentiality phrase and choose Run search.
   Switch between Contains the passage and Not found in extracted text. The
   unverifiable group stays separate; positive results open source page text.

[Demo fixtures](examples/synthetic-contracts/README.md) are synthetic; their manifest
records hashes and expectations. Processing and retrieval results are not fabricated.
The real API smoke script (Python 3.12+, standard library only) creates four new
synthetic documents per invocation and checks upload, original bytes, worker,
derivatives and search classification without deleting existing records:

```sh
python3 scripts/demo_smoke.py
```

It requires a running worker and exits nonzero on failure; records created before
failure remain. Use an [isolated demo stack](docs/demo.md#fresh-validation-stack)
to separate demonstrations and tests from normal data.

## Development and checks

Use Python 3.13 (minimum 3.12), Node 20.19+ or 22+, and npm. Python lock files were
created with Python 3.13. Local OCR tests need Tesseract with English installed,
for example `sudo apt-get install tesseract-ocr tesseract-ocr-eng` on Debian/Ubuntu.
Containers include English and German; set `OCR_LANGUAGES=eng+deu` for both.
Defaults are 30 seconds per OCR call and 100 pages per job. Actual parameters and
engine versions are recorded per run.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.lock
.venv/bin/pip install --no-deps -e backend
npm ci --prefix frontend

.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
npm run build --prefix frontend
npm run format:check --prefix frontend
```

Integration tests require a **separate** PostgreSQL database on port 55432.
Fixtures clear its document tables before each test. Never point tests at the app
database; the test database name must end in `_test`.

```sh
docker compose -f compose.test.yaml up -d --wait
TEST_DATABASE_URL=postgresql+psycopg://traystack:traystack_test@127.0.0.1:55432/traystack_test .venv/bin/pytest backend/tests -q
docker compose -f compose.test.yaml down
```

Prepare the model once and set `SEMANTIC_MODEL_PATH=data/models/minilm` on pytest
invocations to include real-model checks:

```sh
.venv/bin/python -m traystack.prepare_semantic_model data/models/minilm
```

Without that variable real-model tests explicitly skip; filter/API contract tests
remain independent. Without `TEST_DATABASE_URL`, database tests explicitly skip.
Test PostgreSQL uses temporary memory storage and loses data when removed. A fresh
instance tests migrations from an empty database. Storage tests need no database.

Browser tests create synthetic records. Use a separate stack and
`TRAYSTACK_BASE_URL` for controlled collection sizes; see the
[performance report](docs/search-performance.md).

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

Or use installed Chrome:

```sh
cd frontend
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm run test:e2e
```

For frontend development, `npm run dev --prefix frontend` proxies API calls to
`localhost:8000`. For backend development, set `DATABASE_URL` and `STORAGE_PATH`,
run `.venv/bin/alembic -c backend/alembic.ini upgrade head`, then
`.venv/bin/uvicorn traystack.main:app --reload`. Start
`.venv/bin/python -m traystack.worker` in another terminal with matching DB/storage
settings. Do not substitute SQLite.

After replacing only the API container, a 502 can require
`docker compose restart frontend` so Nginx resolves the new internal API address.
Regenerate fixtures with `.venv/bin/python scripts/generate_fixtures.py`.
Update Python locks using pip-tools and `backend/pyproject.toml`; maintain the
frontend lock with npm.

## Architecture and limitations

FastAPI, SQLAlchemy/Alembic and PostgreSQL store relationships/metadata. A local
SHA-256-addressed file store preserves original bytes. React displays real API data;
Nginx serves the built client and proxies requests.

[Architecture](docs/architecture.md), [decisions](docs/decisions.md) and
[demo evidence](docs/demo.md) describe the local implementation.
[Presentation](docs/presentation.md) and [production proposal](docs/production.md)
distinguish delivered features from Azure, Microsoft comparison and pilot proposals.
The [implementation brief](TrayStack_Codex_Instructions.md) contains the broader plan.
Textual/semantic comparison, saved decisions and durable search runs are delivered;
convenient revision-management UI remains a possible extension.

The local prototype has no authentication, tenant isolation or legal contract
assessment. Use synthetic demo data. A review flag is not completed human review.
Complete processing and high OCR scores do not guarantee correct recognition;
handwriting needs original inspection. Empty/failed pages are conservatively
incomplete. “Not found” describes selected extracted text, not legal clause absence.

## Recover a job after a worker crash

There are no automatic retries or timed lease takeovers. A hard crash leaves the
job `running`, preventing another active run for that revision. **Stop all workers
first**, then mark interrupted jobs failed:

```sh
docker compose stop worker
docker compose run --rm --no-deps worker python -m traystack.worker --recover-running
docker compose start worker
```

Retry the failed job as a new run in the interface. Recovery retains selected text
and existing artifacts. Normal worker shutdown waits up to 45 seconds for the
current job; larger OCR runs may take longer and need this recovery procedure.

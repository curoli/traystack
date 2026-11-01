# Demo and validation evidence — milestone 4

## Fresh validation stack

Run from the repository root with Docker/Compose v2 and Python 3.12+. A separate
project name and ports isolate demo data. A new project creates new volumes.
Build needs registry access; the running app needs no external services.

```sh
WEB_PORT=18080 API_PORT=18000 docker compose -p traystack-m4-review up -d --build --wait
python3 scripts/demo_smoke.py --base-url http://localhost:18080
```

Open <http://localhost:18080>. The script prints a prefix such as `Demo 02aa7981`
used in four document titles. It checks real uploads, identical original downloads,
worker/OCR, JSON/Markdown and A/P positive, D negative, E unverifiable results,
fully paginating lists. Each invocation creates four more records. This does not
replace browser focus/usability tests.

Run browser checks against that exact stack:

```sh
TRAYSTACK_BASE_URL=http://localhost:18080 PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome npm run test:e2e --prefix frontend
```

Alternatively install Playwright Chromium as in README and omit the executable
variable. Browser checks create more synthetic records. Prepare a presentation
before these tests, or use another unused project/ports. Stop while retaining data:

```sh
docker compose -p traystack-m4-review down
```

Never use `down -v` on the normal stack to clean up a demo. Reusing a project name
reuses its volumes; choose a previously unused name for an empty collection.

## Presentation and fallback

Use the [18-minute guide](presentation.md) with a six-minute live demo. Process the
four fixtures in advance; reprocessing A can be live. The target appears below and
in the fixture manifest. If the stack is unavailable, explain architecture and
recorded evidence; do not present screenshots as live processing. For worker
problems, show status/errors and README recovery. Failed/uncertain documents still
require review.

## Repeatable walkthrough

1. Start `docker compose up --build`; migrations must succeed and API, PostgreSQL,
   web and the separate worker run. Open <http://localhost:8080>. Existing data remains.
2. Upload `examples/synthetic-contracts/A-confidentiality.pdf` with a title.
   Inspect document, revision 1 and unchanged original.
3. Choose Start processing. Watch queued/running become processed. Coverage and
   quality appear separately: one page processed, no known issue.
4. Open View page text. The clause comes from the real PDF text layer. New JSON
   and Markdown artifacts expose source, job, method/hash and actual preview bytes.
5. Download original and compare bytes/hash with the input.
6. Upload/process `D-delivery.pdf` without the clause, then `P-printed-scan.jpg`.
   Tesseract really runs; page text names OCR and mean word score, not legal confidence.
7. Upload/process `E-difficult-scan.jpg` with Manual review required. It remains
   separately flagged despite complete coverage. Inspect the original; there is
   no button certifying legal correctness of OCR.
8. Reprocess the digital PDF. A new job and two artifacts appear; earlier artifacts
   remain and text details identify the newly selected job.
9. Expand Processing runs for parameters, engine and normalization versions.
   Failures show fixed error codes and retain any previously selected text.
10. Reload, then use Literal search in normalized mode for
    `The receiving party shall not disclose confidential information`.
    A/P match, D appears under Not found in extracted text, E is unverifiable.
11. Upload another document without processing: it remains unverifiable, not negative.
12. Open View page 1 on a positive. Quality and originals remain available.
    After reprocessing, an old literal occurrence requests a new search rather
    than opening mismatched text.

The difficult fixture is degraded print, not an evaluation of historical
handwriting. Manifest expectations test actual results; the app calculates matches
only from selected text. Later features are described in the [user guide](user-guide.md).

## API demo

Upload from the repository root:

```sh
curl --fail http://localhost:8000/api/health
curl --fail -X POST http://localhost:8000/api/documents/upload \
  -F 'title=Confidentiality agreement' \
  -F 'metadata={"company":"Example Company"}' \
  -F 'file=@examples/synthetic-contracts/A-confidentiality.pdf'
```

Replace placeholders with revision/artifact IDs from the response:

```sh
curl --fail -X POST http://localhost:8000/api/revisions/REVISION-ID/process \
  -H 'Content-Type: application/json' -d '{"source_artifact_id":"ARTIFACT-ID"}'
curl --fail http://localhost:8000/api/jobs/JOB-ID
curl --fail http://localhost:8000/api/revisions/REVISION-ID/text
curl --fail http://localhost:8000/api/artifacts/ARTIFACT-ID/content -o /tmp/traystack-original.pdf
sha256sum examples/synthetic-contracts/A-confidentiality.pdf /tmp/traystack-original.pdf
```

Starting while another run is active returns 409. `POST /api/jobs/JOB-ID/retry`
creates a new attempt with inherited parameters plus newly introduced review flags.
For different OCR languages/limits, start fresh processing rather than retrying old
parameters unchanged.

```sh
curl --fail -X POST http://localhost:8000/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"The receiving party shall not disclose confidential information","mode":"normalized","relation":"lacks","scope":"latest","limit":25}'
```

See the [search contract](search.md) for statuses, separate pagination and offsets.

## Checks and recorded milestone evidence

Exact commands are in README. Backend tests use dedicated PostgreSQL, migrations
and real printed-scan OCR. Coverage includes mixed/inline PDFs, offsets, foreign
sources, concurrent claims, timeouts/engine failures, failed publication, retained
old text and retries. Simulated failures supplement real success paths. Controlled
canonical fixtures cover additional search cases; end-to-end checks upload PDF/JPEG,
run the actual worker, search and download originals.

Recovery is explicit, without automatic retries/timed takeover. Multi-frame images
are rejected rather than treating frame 1 as the entire document. Empty pages
conservatively require review.

Historical milestone run on **30 October 2026**:

- Fresh `traystack-m4-review` PostgreSQL/blob volumes: build, both migrations then
  present and healthy startup passed. Normal data was preserved; backend tests also
  used disposable PostgreSQL 17.
- Smoke script: four uploads, original bytes, real extraction/OCR, derivatives and
  expected classification passed. No Azure/SharePoint call or handwriting evaluation.
- **102 backend tests**, none skipped: real OCR, mixed/inline PDFs, claims/atomic
  publication, latest revisions, negative/unverifiable pagination, Unicode and
  concurrent-publication snapshot checks.
- **Nine Chrome/Playwright scenarios**: upload/download, processing, desktop/mobile
  navigation, literal search, repeated page opening, stale occurrences and local API
  explorer. One isolated renderer test covered code-point highlighting; others used
  the real stack.
- TypeScript, Vite, Ruff, Prettier, diff checks, `alembic check` and `pip check` passed.
  Starlette's HTTPX TestClient deprecation warning remained, without runtime impact.

English-interface validation, also **30 October 2026**:

- All **eleven** Chrome/Playwright scenarios passed on port 8080, including real OCR,
  repeated page navigation and a real invalid PDF upload.
- German browser locale checks confirmed `lang="en"`, English title/date display
  and unchanged German document titles. Dates use English months and 24-hour time
  in the browser timezone.
- Isolated checks covered Unicode, network errors and structured-validation fallback;
  successful processing was not simulated.
- TypeScript, Vite, Prettier, diff checks and visual inspection passed. Backend/model/
  search semantics were unchanged; the 102 backend tests were not rerun for that
  frontend-only change. These are historical counts, not today's complete suite.

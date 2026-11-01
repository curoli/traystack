# TrayStack technology stack

This inventory describes the implemented app, not a proposed stack. Versions come
from [Python runtime dependencies](backend/requirements.lock),
[Python development dependencies](backend/requirements-dev.lock),
[npm's lockfile](frontend/package-lock.json), [Compose](compose.yaml), and the
[backend](backend/Dockerfile) / [frontend](frontend/Dockerfile) Dockerfiles.
Container and host versions below were observed on 1 November 2026. They are not
claims about the latest upstream release.

The advantages column explains why a choice fits this project. These are
engineering judgments, not universal performance rankings. Each technology name
links to its official documentation or upstream project.

## Runtime and deployment

| Technology | Type | Version used | Role and advantage compared with alternatives |
| --- | --- | --- | --- |
| [Python](https://docs.python.org/3.13/) | Language / interpreter binary | Docker: 3.13 (`3.13.18` observed); package requires ≥3.12 | API, processing worker, matching and evaluation share one language and its PDF/OCR/ML libraries. This avoids a separate inference service and cross-language pipeline for this app. |
| [PostgreSQL](https://www.postgresql.org/docs/17/index.html) | Database server binary / container | `postgres:17` (`17.9` observed) | Documents, jobs, provenance, decisions and saved snapshots share transactional storage. Row locking, repeatable-read snapshots and JSONB suit concurrent workers and reproducible search better than an embedded SQLite deployment. A separate document database would split transactional state. |
| [Docker Engine](https://docs.docker.com/engine/) | Container runtime / host binary | `29.9.2` observed; no exact version pinned by repo | Packages Python, OCR binaries and web serving consistently rather than requiring each developer to install them manually. Adds container build/storage overhead. |
| [Docker Compose](https://docs.docker.com/compose/) | Host CLI / service orchestration | `5.6.1` observed; repo uses the Compose specification | Starts database, migrations, API, worker and frontend with dependency checks and volumes. Less operational setup than Kubernetes for a local, single-host demo. It is not a multi-host scheduler. |
| [NGINX unprivileged image](https://github.com/nginx/docker-nginx-unprivileged) | Web-server binary / container | `nginxinc/nginx-unprivileged:stable-alpine` (`NGINX 1.30.6` observed) | Serves compiled static assets and proxies `/api` from one origin without running Node in production. The unprivileged image runs without a root web-server process. |
| [Node.js](https://nodejs.org/docs/latest-v22.x/api/) | JavaScript runtime binary, build only | `22-bookworm-slim` image tag | Runs npm, TypeScript, Vite and browser tooling. The production frontend needs only its static output, avoiding a persistent Node server for a client-side app. |
| [Local filesystem + SHA-256](https://docs.python.org/3.13/library/hashlib.html) | Storage design / Python standard library | Python 3.13 implementation | Immutable original/derived blobs live in a Docker volume with checksums and database provenance. Simpler local setup than S3; multi-host operation would require shared/object storage and additional operational work. |

## API, data and document processing

| Technology | Type | Locked version | Role and advantage compared with alternatives |
| --- | --- | --- | --- |
| [FastAPI](https://fastapi.tiangolo.com/features/) | Python web-framework library | `0.162.0` | Typed REST endpoints and generated OpenAPI documentation reduce handwritten validation/docs compared with a minimal Flask setup. A full Django application would bring more framework machinery than this focused API requires. |
| [Uvicorn](https://www.uvicorn.org/) | Python ASGI server / CLI | `0.54.0` | Runs the FastAPI app using its native ASGI interface. A WSGI-only server would need adaptation. |
| [Pydantic](https://docs.pydantic.dev/latest/) | Python validation library | `2.14.2` | Validates requests, search snapshots and responses from typed models rather than scattered dictionary checks. Validation remains necessary despite frontend TypeScript. |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Python configuration library | `2.16.2` | Typed environment-based configuration with validation, avoiding an ad hoc collection of `os.environ` conversions. |
| [SQLAlchemy](https://docs.sqlalchemy.org/en/20/) | Python SQL toolkit / ORM library | `2.0.55` | Shares transaction/session handling and model definitions while retaining explicit SQL expressions for category filters and scope queries. Less repetitive mapping code than raw driver calls throughout the app. |
| [Alembic](https://alembic.sqlalchemy.org/en/latest/) | Python migration library / CLI | `1.20.1` | Versioned schema changes integrate with SQLAlchemy; safer upgrades of existing data than recreating tables or relying on initial schema creation. |
| [Psycopg](https://www.psycopg.org/psycopg3/docs/) | Python PostgreSQL driver with binary distribution | `3.3.6` | PostgreSQL-specific driver used by SQLAlchemy. The binary package simplifies container installation compared with compiling a driver locally. |
| [python-multipart](https://github.com/Kludex/python-multipart) | Python multipart-parser library | `0.0.32` | Supports browser file uploads through FastAPI instead of embedding files as base64 in JSON. |
| [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/) | Python bindings to native MuPDF | `1.28.2` | Extracts PDF text, inspects page images and renders pages within one library. This avoids combining a text-only PDF parser with a separate renderer for OCR. Licensing and deployment constraints still need assessment for a commercial distribution. |
| [Pillow](https://pillow.readthedocs.io/en/stable/) | Python imaging library with native codecs | `12.3.0` | Opens/normalizes image inputs, handles OCR image preparation and generates synthetic fixtures. More focused than introducing OpenCV for basic image operations. |
| [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/) | Native OCR executable + language data | `5.3.0` observed; Debian Bookworm packages `tesseract-ocr`, `-eng`, `-deu` | Performs OCR locally without per-request cloud access or sending contracts to a hosted OCR service. Recognition, particularly handwriting, can be poor; extraction quality/readiness gates remain necessary. |
| [pytesseract](https://github.com/madmaze/pytesseract) | Python wrapper library | `0.3.13` | Calls the Tesseract executable with timeout and structured output support, avoiding handwritten subprocess/output parsing. It does not bundle the OCR binary. |
| [swagger-ui-py](https://github.com/PWZER/swagger-ui-py) | Python package of Swagger UI assets | `25.7.1` | Bundles API documentation assets for local serving rather than requiring a public CDN when opening `/docs`. |

## Textual and semantic matching

| Technology | Type | Version used | Role and advantage compared with alternatives |
| --- | --- | --- | --- |
| [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/) | Python library with native matching implementation | `3.14.6` | Character-edit similarity for bounded candidate windows with offsets and textual differences. More suitable than a pure-Python edit-distance loop for repeated comparisons; embeddings alone cannot supply the same literal character comparison. Retrieval still has explicit work limits. |
| [ONNX Runtime](https://onnxruntime.ai/docs/) | Native inference runtime / Python library | `1.31.1` | Runs the quantized embedding model locally on CPU without a full PyTorch runtime or hosted embedding API in the request path. A larger model/service could improve some semantic judgments at higher resource/operational cost. |
| [Multilingual MiniLM, Xenova ONNX conversion](https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2) | Pretrained embedding model, quantized INT8 ONNX artifact | Revision `2c4055b12046f11709e9df2c122e59ffbdc2f900` | Multilingual sentence embeddings fit the English/German corpus and CPU-only local deployment. Compared with a large generative model it needs fewer resources and has no generated-answer step. Scores do not establish legal equivalence; the pipeline rejects overlong input rather than silently truncating it. |
| [Hugging Face Tokenizers](https://huggingface.co/docs/tokenizers/index) | Python library with native tokenizer | `0.23.3` | Loads the model's pinned tokenizer directly, avoiding a full Transformers/PyTorch stack solely for tokenization. |
| [NumPy](https://numpy.org/doc/) | Python numerical-array library | `2.5.4` | Array operations for model pooling, normalization and score calculation instead of Python loops over embedding coordinates. |

The model and tokenizer have pinned SHA-256 hashes in
[semantic_model.py](backend/traystack/semantic_model.py). Model downloads occur at
setup/build time. Search first retrieves textually similar windows, then embeds
the query and those windows; there is no vector database or generative LLM in the
implemented search path. A PostgreSQL-backed Python worker processes jobs without
adding Redis/Celery infrastructure; this suits the current workload but does not
provide their distributed task orchestration features.

## Frontend and verification

| Technology | Type | Locked version | Role and advantage compared with alternatives |
| --- | --- | --- | --- |
| [React + React DOM](https://react.dev/) | JavaScript UI libraries | `19.3.1` each | Reusable search/review/source components and state-driven updates avoid manual DOM synchronization. A server-rendering framework is unnecessary for this local interactive app. |
| [TypeScript](https://www.typescriptlang.org/) | Language / npm compiler tool | `5.9.3` | Checks API-facing types and component contracts before build, catching mistakes that plain JavaScript leaves to runtime. |
| [Vite](https://vite.dev/guide/) | npm development server / build tool | `6.4.5` | Provides local development and a static production bundle with little custom bundler configuration. The app does not require an SSR framework. |
| [Playwright Test](https://playwright.dev/docs/intro) | npm browser-automation library / test runner | `1.64.1` | Exercises real navigation, focus, stale requests and saves through the browser and API; these failures can escape component-only tests. The repo uses Chromium, optionally via a system Chrome executable. |
| [pytest](https://docs.pytest.org/) | Python testing library / CLI | `9.2.0` | Fixtures and parametrization cover processing, retrieval and PostgreSQL integration with less setup repetition than handwritten test scripts. |
| [HTTPX](https://www.python-httpx.org/) | Python HTTP-client library, development | `0.28.1` | Supports the FastAPI test client and API checks instead of maintaining a separate HTTP harness. |
| [Ruff](https://docs.astral.sh/ruff/) | Native lint/format CLI distributed as Python package | `0.17.3` | One configured tool handles Python formatting and selected lint rules instead of separately configuring several tools. |
| [Prettier](https://prettier.io/docs/) | npm formatter / CLI | `3.9.10` | Consistent TypeScript, JSX and CSS formatting avoids manual style decisions across UI changes. |

## Version boundaries and maintenance

The lockfiles specify resolved application dependencies; `package.json` and
`pyproject.toml` describe allowed ranges. Install with `npm ci` and the appropriate
Python lockfile to reproduce those versions. This table intentionally omits most
transitive packages; the lockfiles are the complete inventories.

Container tags are floating within their named tracks: Python 3.13, Node 22,
PostgreSQL 17 and NGINX stable. Debian OCR packages and host Docker tools are not
patch-pinned either. A later rebuild may produce different observed binary
versions. For a fully reproducible release, also record/pin image digests and OS
packages. Updating this inventory does not itself upgrade any dependency.

Useful checks against a running app:

```sh
docker compose exec api python --version
docker compose exec api tesseract --version
docker compose exec postgres postgres --version
docker compose exec frontend nginx -v
docker compose version
docker version
```

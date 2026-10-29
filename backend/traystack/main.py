import json
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import distribution
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from traystack.config import Settings
from traystack.db import get_session
from traystack.models import Artifact, Document, Revision
from traystack.schemas import ArtifactOut, DocumentList, DocumentOut, HealthOut, RevisionOut
from traystack.services.ingestion import safe_filename, validate_file
from traystack.services.storage import InvalidUpload, LocalStorage, UploadTooLarge

logger = logging.getLogger(__name__)
SessionDep = Annotated[Session, Depends(get_session)]


def serialize_document(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        metadata=document.metadata_json,
        created_at=document.created_at,
        updated_at=document.updated_at,
        revisions=[RevisionOut.model_validate(revision) for revision in document.revisions],
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(
            config.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
        )
        app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
        app.state.storage = LocalStorage(config.storage_path)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="TrayStack", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.mount(
        "/api/docs-assets",
        StaticFiles(directory=distribution("swagger-ui-py").locate_file("swagger_ui/static")),
        name="docs-assets",
    )

    @app.get("/docs", include_in_schema=False)
    def docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="TrayStack API",
            swagger_js_url="/api/docs-assets/swagger-ui-bundle.js",
            swagger_css_url="/api/docs-assets/swagger-ui.css",
            swagger_favicon_url="/api/docs-assets/favicon-32x32.png",
            swagger_ui_parameters={"validatorUrl": None},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        # Do not log SQL parameters, which may include uploaded contract metadata.
        logger.error("Database operation failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database is unavailable"})

    @app.exception_handler(OSError)
    async def storage_error(request: Request, error: OSError) -> JSONResponse:
        logger.error("Storage operation failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "File storage is unavailable"})

    @app.get("/api/health", response_model=HealthOut)
    def health(request: Request, session: SessionDep):
        database, storage = "ok", "ok"
        try:
            # Readiness checks the schema as well as connectivity.
            session.execute(text("SELECT id FROM documents LIMIT 1"))
        except SQLAlchemyError:
            database = "unavailable"
        try:
            with tempfile.TemporaryFile(dir=request.app.state.storage.root):
                pass
        except OSError:
            storage = "unavailable"
        ok = database == storage == "ok"
        return JSONResponse(
            status_code=200 if ok else 503,
            content=HealthOut(
                status="ok" if ok else "unavailable", database=database, storage=storage
            ).model_dump(),
        )

    @app.post("/api/documents/upload", response_model=DocumentOut, status_code=201)
    def upload(
        request: Request,
        session: SessionDep,
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1, max_length=300)],
        metadata: Annotated[str, Form(max_length=16384)] = "{}",
        requires_manual_review: Annotated[bool, Form()] = False,
    ):
        title = title.strip()
        if not title or "\x00" in title:
            raise HTTPException(422, "Title must contain printable text")
        try:
            values = json.loads(metadata)
            # Reject non-JSON numbers and unpaired surrogate characters before PostgreSQL.
            json.dumps(values, allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, RecursionError):
            raise HTTPException(422, "Metadata must be a JSON object") from None
        if not isinstance(values, dict):
            raise HTTPException(422, "Metadata must be a JSON object")
        # PostgreSQL JSONB rejects U+0000, including nested values and keys.
        pending: list[object] = [values]
        while pending:
            value = pending.pop()
            if isinstance(value, str) and "\x00" in value:
                raise HTTPException(422, "Metadata cannot contain null characters")
            if isinstance(value, dict):
                pending.extend(value)
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        filename = safe_filename(file.filename)
        # Check size before any parser reads the full source. UploadFile is spooled to disk.
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > config.upload_max_bytes:
            raise HTTPException(413, "File exceeds upload size limit")
        if size == 0:
            raise HTTPException(422, "Empty files are not supported")
        try:
            mime_type = validate_file(file.file, filename)
            blob = request.app.state.storage.put_stream(file.file, config.upload_max_bytes)
        except UploadTooLarge as error:
            raise HTTPException(413, str(error)) from None
        except InvalidUpload as error:
            raise HTTPException(422, str(error)) from None
        # Publish bytes first; only committed metadata makes a blob retrievable.
        # Failed DB commits can leave an unreferenced blob; never delete a shared blob here.
        document = Document(title=title, metadata_json=values)
        revision = Revision(revision_number=1, document=document)
        Artifact(
            revision=revision,
            kind="original",
            mime_type=mime_type,
            original_filename=filename,
            storage_key=blob.storage_key,
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            processor="upload",
            parameters={"requires_manual_review": requires_manual_review},
        )
        session.add(document)
        session.commit()
        return serialize_document(document)

    @app.get("/api/documents", response_model=DocumentList)
    def documents(
        session: SessionDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        query = (
            select(Document)
            .options(selectinload(Document.revisions).selectinload(Revision.artifacts))
            .order_by(Document.created_at.desc(), Document.id)
            .limit(limit)
            .offset(offset)
        )
        return DocumentList(
            items=[serialize_document(doc) for doc in session.scalars(query)],
            total=session.scalar(select(func.count()).select_from(Document)),
            limit=limit,
            offset=offset,
        )

    @app.get("/api/documents/{document_id}", response_model=DocumentOut)
    def document(document_id: UUID, session: SessionDep):
        result = session.get(Document, document_id)
        if result is None:
            raise HTTPException(404, "Document not found")
        return serialize_document(result)

    @app.get("/api/revisions/{revision_id}", response_model=RevisionOut)
    def revision(revision_id: UUID, session: SessionDep):
        result = session.get(Revision, revision_id)
        if result is None:
            raise HTTPException(404, "Revision not found")
        return result

    @app.get("/api/artifacts/{artifact_id}", response_model=ArtifactOut)
    def artifact(artifact_id: UUID, session: SessionDep):
        result = session.get(Artifact, artifact_id)
        if result is None:
            raise HTTPException(404, "Artifact not found")
        return result

    @app.get("/api/artifacts/{artifact_id}/content")
    def content(artifact_id: UUID, request: Request, session: SessionDep):
        result = session.get(Artifact, artifact_id)
        if result is None:
            raise HTTPException(404, "Artifact not found")
        path = request.app.state.storage.path_for(result.storage_key)
        if not path.is_file():
            raise HTTPException(503, "Artifact bytes are unavailable")
        return FileResponse(
            path,
            media_type=result.mime_type,
            filename=safe_filename(result.original_filename),
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    return app


app = create_app()

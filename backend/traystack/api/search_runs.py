from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.models import SearchRun
from traystack.review_schemas import ReviewFilter
from traystack.run_schemas import RunCreate, RunName, RunSummary
from traystack.schemas import TextContentOut
from traystack.services.search_runs import archived_source, create_run, get_run, read_run
from traystack.services.semantic import SemanticInputTooLong, SemanticUnavailable, get_engine
from traystack.services.textual_matching import SearchTooBroad
from traystack.textual_schemas import TextualSearchRequest, TextualSearchResponse

router = APIRouter(prefix="/api/search-runs", tags=["saved searches"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=TextualSearchResponse, status_code=201)
def create(payload: RunCreate, request: Request):
    config = request.app.state.settings
    try:
        return create_run(
            request.app.state.session_factory,
            payload,
            lambda: get_engine(config.semantic_model_path, config.storage_path / "embedding-cache"),
            config.search_snapshot_max_bytes,
            config.search_snapshot_max_documents,
        )
    except SearchTooBroad as error:
        raise HTTPException(422, error.detail()) from None
    except SemanticInputTooLong as error:
        raise HTTPException(422, str(error)) from None
    except SemanticUnavailable as error:
        raise HTTPException(503, str(error)) from None


@router.get("")
def list_runs(
    session: SessionDep,
    limit: int = Query(ge=1, le=50, default=20),
    offset: int = Query(ge=0, default=0),
):
    # List metadata without loading potentially large result JSON.
    rows = session.execute(
        select(*(getattr(SearchRun, field) for field in RunSummary.model_fields))
        .order_by(SearchRun.created_at.desc(), SearchRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings()
    return {
        "items": [RunSummary.model_validate(row) for row in rows],
        "total": session.scalar(select(func.count()).select_from(SearchRun)),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{identity}", response_model=TextualSearchResponse)
def read(
    identity: UUID,
    session: SessionDep,
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0),
    occurrence_limit: int = Query(default=5, ge=1, le=25),
    occurrence_offset: int = Query(default=0, ge=0),
    document_id: UUID | None = None,
    review_filter: ReviewFilter | None = None,
    unsearchable_limit: int = Query(default=10, ge=1, le=100),
    unsearchable_offset: int = Query(default=0, ge=0),
):
    run = get_run(session, identity)
    if occurrence_offset and not (document_id or run.request_json.get("document_id")):
        raise HTTPException(422, "Occurrence paging requires a document from this saved search")
    view = TextualSearchRequest.model_validate(
        {
            **run.request_json,
            "document_id": document_id or run.request_json.get("document_id"),
            "limit": limit,
            "offset": offset,
            "occurrence_limit": occurrence_limit,
            "occurrence_offset": occurrence_offset,
            "unsearchable_limit": unsearchable_limit,
            "unsearchable_offset": unsearchable_offset,
        }
    )
    return read_run(session, identity, view, review_filter)


@router.get("/{identity}/scope")
def scope(
    identity: UUID,
    session: SessionDep,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    run = get_run(session, identity)
    return {
        "items": run.scope_json[offset : offset + limit],
        "total": len(run.scope_json),
        "limit": limit,
        "offset": offset,
    }


@router.post("/{identity}/name", response_model=RunSummary)
def rename(identity: UUID, payload: RunName, session: SessionDep):
    run = get_run(session, identity)
    run.name = payload.name
    session.commit()
    return run


@router.get("/{identity}/sources/{job_id}", response_model=TextContentOut)
def source(identity: UUID, job_id: UUID, session: SessionDep):
    return archived_source(session, identity, job_id)

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.search_schemas import SearchRequest, SearchResponse
from traystack.services.query_guidance import assess_query
from traystack.services.search import search_snapshot
from traystack.services.semantic import SemanticInputTooLong, SemanticUnavailable, get_engine
from traystack.services.textual_matching import SearchTooBroad
from traystack.services.textual_search import textual_snapshot
from traystack.textual_schemas import (
    TextualAssessment,
    TextualAssessmentRequest,
    TextualSearchRequest,
    TextualSearchResponse,
)

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, session: Annotated[Session, Depends(get_session)]):
    return search_snapshot(session, payload)


@router.post("/search/textual", response_model=TextualSearchResponse)
def textual_search(
    payload: TextualSearchRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
):
    try:
        config = request.app.state.settings
        return textual_snapshot(
            session,
            payload,
            semantic_provider=lambda: get_engine(
                config.semantic_model_path, config.storage_path / "embedding-cache"
            ),
        )
    except SearchTooBroad as error:
        raise HTTPException(422, error.detail()) from None
    except SemanticInputTooLong as error:
        raise HTTPException(422, str(error)) from None
    except SemanticUnavailable as error:
        raise HTTPException(503, str(error)) from None


@router.post("/search/textual/assess", response_model=TextualAssessment)
def assess_textual_query(payload: TextualAssessmentRequest):
    return assess_query(payload)

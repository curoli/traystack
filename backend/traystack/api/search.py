from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.search_schemas import SearchRequest, SearchResponse
from traystack.services.search import search_snapshot
from traystack.services.textual_matching import SearchTooBroad
from traystack.services.textual_search import textual_snapshot
from traystack.textual_schemas import TextualSearchRequest, TextualSearchResponse

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, session: Annotated[Session, Depends(get_session)]):
    return search_snapshot(session, payload)


@router.post("/search/textual", response_model=TextualSearchResponse)
def textual_search(
    payload: TextualSearchRequest, session: Annotated[Session, Depends(get_session)]
):
    try:
        return textual_snapshot(session, payload)
    except SearchTooBroad as error:
        raise HTTPException(422, str(error)) from None

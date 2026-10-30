from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.search_schemas import SearchRequest, SearchResponse
from traystack.services.search import search_snapshot

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, session: Annotated[Session, Depends(get_session)]):
    return search_snapshot(session, payload)

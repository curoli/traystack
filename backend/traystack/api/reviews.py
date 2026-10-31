from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.review_schemas import ReviewOut, ReviewWrite
from traystack.services.reviews import save_review

router = APIRouter(prefix="/api", tags=["reviews"])


@router.post("/reviews", response_model=ReviewOut)
def review(payload: ReviewWrite, session: Annotated[Session, Depends(get_session)]):
    return save_review(session, payload)

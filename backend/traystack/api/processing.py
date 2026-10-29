from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from traystack.db import get_session
from traystack.models import Artifact, ProcessingJob, Revision, RevisionText
from traystack.schemas import JobOut, ProcessRequest, TextContentOut
from traystack.services.normalization import NORMALIZATION_VERSION

router = APIRouter(prefix="/api", tags=["processing"])
SessionDep = Annotated[Session, Depends(get_session)]


def review_required(session: Session, source: Artifact, requested: bool) -> bool:
    if requested or source.parameters.get("requires_manual_review"):
        return True
    return (
        session.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.source_artifact_id == source.id,
                ProcessingJob.parameters["requires_manual_review"].as_boolean().is_(True),
            )
            .limit(1)
        )
        is not None
    )


def save_job(session: Session, job: ProcessingJob) -> ProcessingJob:
    session.add(job)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if getattr(error.orig.diag, "constraint_name", None) == "uq_active_job_per_revision":
            raise HTTPException(
                409, "A job is already queued or running for this revision"
            ) from None
        raise
    return job


@router.post("/revisions/{revision_id}/process", response_model=JobOut, status_code=202)
def process(revision_id: UUID, payload: ProcessRequest, request: Request, session: SessionDep):
    revision = session.get(Revision, revision_id)
    if revision is None:
        raise HTTPException(404, "Revision not found")
    if payload.source_artifact_id is None:
        originals = session.scalars(
            select(Artifact).where(Artifact.revision_id == revision_id, Artifact.kind == "original")
        ).all()
        if len(originals) != 1:
            raise HTTPException(422, "Choose an explicit original source artifact")
        source = originals[0]
    else:
        source = session.get(Artifact, payload.source_artifact_id)
    if source is None or source.revision_id != revision_id or source.kind != "original":
        raise HTTPException(422, "Source must be an original artifact of this revision")
    if source.mime_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise HTTPException(422, "Unsupported source type")
    settings = request.app.state.settings
    parameters = {
        "ocr_languages": settings.ocr_languages,
        "ocr_timeout_seconds": settings.ocr_timeout_seconds,
        "ocr_dpi": settings.ocr_dpi,
        "max_pages": settings.processing_max_pages,
        "max_pixels": settings.processing_max_pixels,
        "ocr_min_mean_confidence": 80,
        "requires_manual_review": review_required(session, source, payload.requires_manual_review),
    }
    return save_job(
        session,
        ProcessingJob(
            revision_id=revision_id,
            source_artifact_id=source.id,
            normalization_version=NORMALIZATION_VERSION,
            parameters=parameters,
        ),
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: UUID, session: SessionDep):
    result = session.get(ProcessingJob, job_id)
    if result is None:
        raise HTTPException(404, "Job not found")
    return result


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry(job_id: UUID, session: SessionDep):
    previous = session.get(ProcessingJob, job_id)
    if previous is None:
        raise HTTPException(404, "Job not found")
    if previous.status != "failed":
        raise HTTPException(409, "Only failed jobs can be retried")
    parameters = dict(previous.parameters)
    source = session.get(Artifact, previous.source_artifact_id)
    parameters["requires_manual_review"] = review_required(
        session, source, bool(parameters.get("requires_manual_review"))
    )
    return save_job(
        session,
        ProcessingJob(
            revision_id=previous.revision_id,
            source_artifact_id=previous.source_artifact_id,
            retry_of_job_id=previous.id,
            parameters=parameters,
            normalization_version=previous.normalization_version,
        ),
    )


@router.get("/revisions/{revision_id}/text", response_model=TextContentOut)
def text_content(revision_id: UUID, session: SessionDep):
    result = session.get(RevisionText, revision_id)
    if result is None:
        raise HTTPException(404, "No selected extraction for this revision")
    return result

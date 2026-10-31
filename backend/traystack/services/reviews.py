"""Persist a shared review decision with source validation and optimistic concurrency."""

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from traystack.models import Document, PassageReview, Revision, RevisionText
from traystack.review_schemas import ReviewOut, ReviewWrite
from traystack.services.normalization import NORMALIZATION_VERSION, normalize_for_search
from traystack.services.passage_identity import occurrence_identity, text_fingerprint
from traystack.services.textual_matching import CANDIDATE_POLICY, SCORER_VERSION


def validate_current(session, payload):
    # Serialize against new revisions and publication of another selected text.
    document = session.scalar(
        select(Document).where(Document.id == payload.document_id).with_for_update()
    )
    latest = session.scalar(
        select(Revision.id)
        .where(Revision.document_id == payload.document_id)
        .order_by(Revision.revision_number.desc())
        .limit(1)
    )
    current = session.scalar(
        select(RevisionText)
        .where(RevisionText.revision_id == payload.revision_id)
        .with_for_update()
    )
    if (
        document is None
        or latest != payload.revision_id
        or current is None
        or current.processing_job_id != payload.processing_job_id
        or current.source_artifact_id != payload.source_artifact_id
        or current.normalization_version != payload.normalization_version
    ):
        raise HTTPException(
            409, "The selected source has changed. Please run the search again before reviewing."
        )
    if (
        payload.scorer_version != SCORER_VERSION
        or payload.candidate_policy != CANDIDATE_POLICY
        or (payload.mode == "normalized" and current.normalization_version != NORMALIZATION_VERSION)
    ):
        raise HTTPException(409, "The comparison method has changed. Please run the search again.")
    phrase = normalize_for_search(payload.query) if payload.mode == "normalized" else payload.query
    content = current.normalized_text if payload.mode == "normalized" else current.plain_text
    identity = occurrence_identity(
        current.processing_job_id, payload.mode, phrase, payload.start_offset, payload.end_offset
    )
    if (
        payload.end_offset > len(content)
        or payload.occurrence_id != identity
        or text_fingerprint(content[payload.start_offset : payload.end_offset])
        != payload.matched_sha256
    ):
        raise HTTPException(
            409, "The passage does not match the selected source. Please run the search again."
        )
    return phrase, identity


def validate_saved(session, payload):
    from traystack.services.search_runs import archived_source, get_run

    run = get_run(session, payload.search_run_id)
    group = next(
        (
            g
            for g in run.result_json["results"]
            if g["document"]["document_id"] == str(payload.document_id)
        ),
        None,
    )
    item = (
        next(
            (
                item
                for item in group["occurrences"]
                if item["occurrence_id"] == payload.occurrence_id
            ),
            None,
        )
        if group
        else None
    )
    fields = {
        "revision_id": "revision_id",
        "processing_job_id": "processing_job_id",
        "source_artifact_id": "artifact_id",
        "normalization_version": "normalization_version",
    }
    if (
        item is None
        or any(
            str(getattr(payload, key)) != str(group["document"][value])
            for key, value in fields.items()
        )
        or payload.query != run.result_json["query"]
        or payload.mode != run.result_json["mode"]
        or payload.scorer_version != run.result_json["scorer_version"]
        or payload.candidate_policy != run.result_json["candidate_policy"]
        or any(
            getattr(payload, key) != item[key]
            for key in ["start_offset", "end_offset", "matched_sha256"]
        )
    ):
        raise HTTPException(409, "This passage does not belong to the saved search")
    source = archived_source(session, run.id, payload.processing_job_id)
    content = source["normalized_text"] if payload.mode == "normalized" else source["plain_text"]
    if (
        text_fingerprint(content[payload.start_offset : payload.end_offset])
        != payload.matched_sha256
    ):
        raise HTTPException(503, "Saved passage integrity check failed")
    return run.result_json["effective_query"], item["occurrence_id"]


def save_review(session, payload: ReviewWrite) -> ReviewOut:
    phrase, identity = (
        validate_saved(session, payload)
        if payload.search_run_id
        else validate_current(session, payload)
    )
    if payload.expected_version == 0:
        values = payload.model_dump(
            exclude={"document_id", "query", "expected_version", "search_run_id"}
        )
        values.update(effective_query=phrase, version=1)
        statement = (
            insert(PassageReview)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[PassageReview.occurrence_id])
            .returning(PassageReview)
        )
    else:
        statement = (
            update(PassageReview)
            .where(
                PassageReview.occurrence_id == identity,
                PassageReview.version == payload.expected_version,
                PassageReview.matched_sha256 == payload.matched_sha256,
                PassageReview.source_artifact_id == payload.source_artifact_id,
                PassageReview.normalization_version == payload.normalization_version,
            )
            .values(
                decision=payload.decision, version=PassageReview.version + 1, updated_at=func.now()
            )
            .returning(PassageReview)
        )
    result = session.scalar(statement)
    if result is None:
        raise HTTPException(
            409,
            "This review changed in another view. "
            + (
                "Refresh reviews before saving."
                if payload.search_run_id
                else "Please run the search again before saving."
            ),
        )
    answer = ReviewOut.model_validate(result)
    session.commit()
    return answer

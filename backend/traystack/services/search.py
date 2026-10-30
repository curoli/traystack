"""Full selected-text search. Pagination never determines absence or hides unknown counts."""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from traystack.models import Artifact, Document, PageText, ProcessingJob, Revision, RevisionText
from traystack.search_schemas import (
    SearchJobOut,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchSummary,
)
from traystack.services.normalization import NORMALIZATION_VERSION, normalize_for_search


def search_snapshot(session: Session, request: SearchRequest) -> SearchResponse:
    # A fresh request session must not have run any query before setting isolation.
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    session.execute(text("SET TRANSACTION READ ONLY"))
    searched_at = datetime.now(UTC)
    phrase = normalize_for_search(request.query) if request.mode == "normalized" else request.query
    column = (
        RevisionText.normalized_text if request.mode == "normalized" else RevisionText.plain_text
    )
    statement = selected_scope(phrase, column)
    # PostgreSQL inspects every full selected text. Only metadata and positions are
    # transferred for the whole scope; snippets/page metadata are fetched for returned hits.
    results = [classify(row, request) for row in session.execute(statement).mappings()]
    counts = Counter(result.status for result in results)
    wanted = "found" if request.relation == "contains" else "not_found_in_processed_text"
    matches = [result for result in results if result.status == wanted]
    unknown = [result for result in results if result.status == "unverifiable"]
    visible = matches[request.offset : request.offset + request.limit]
    if wanted == "found":
        add_evidence(session, visible, phrase, column, request.mode)
    return SearchResponse(
        query=request.query,
        effective_query=phrase,
        mode=request.mode,
        relation=request.relation,
        scope=request.scope,
        searched_at=searched_at,
        summary=SearchSummary(
            documents_total=len(results),
            found=counts["found"],
            not_found_in_processed_text=counts["not_found_in_processed_text"],
            unverifiable=counts["unverifiable"],
        ),
        results=visible,
        total=len(matches),
        limit=request.limit,
        offset=request.offset,
        unverifiable=unknown[
            request.unverifiable_offset : request.unverifiable_offset + request.unverifiable_limit
        ],
        unverifiable_total=len(unknown),
        unverifiable_limit=request.unverifiable_limit,
        unverifiable_offset=request.unverifiable_offset,
    )


def selected_scope(phrase, column):
    """One latest revision and its selected-run/quality provenance per document."""
    latest_number = (
        select(func.max(Revision.revision_number))
        .where(Revision.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    latest_job_id = (
        select(ProcessingJob.id)
        .where(ProcessingJob.revision_id == Revision.id)
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
        .limit(1)
        .correlate(Revision)
        .scalar_subquery()
    )
    latest_job = aliased(ProcessingJob, name="latest_job")
    selected_job = aliased(ProcessingJob, name="selected_job")
    flagged_run = (
        select(ProcessingJob.id)
        .where(
            ProcessingJob.source_artifact_id == RevisionText.source_artifact_id,
            ProcessingJob.parameters["requires_manual_review"].as_boolean().is_(True),
        )
        .correlate(RevisionText)
        .exists()
    )
    return (
        select(
            Document.id.label("document_id"),
            Document.title,
            Revision.id.label("revision_id"),
            Revision.revision_number,
            RevisionText.source_artifact_id,
            RevisionText.processing_job_id,
            RevisionText.normalization_version,
            RevisionText.status.label("coverage"),
            RevisionText.quality_status,
            RevisionText.quality_warnings,
            RevisionText.pages_total,
            RevisionText.pages_processed,
            RevisionText.pages_failed,
            selected_job.processor_versions,
            latest_job.id.label("latest_job_id"),
            latest_job.status.label("latest_job_status"),
            latest_job.error_message.label("latest_job_error"),
            or_(
                func.coalesce(Artifact.parameters["requires_manual_review"].as_boolean(), False),
                flagged_run,
            ).label("manual_review"),
            func.strpos(column, phrase).label("position"),
        )
        .select_from(Document)
        .outerjoin(
            Revision,
            and_(Revision.document_id == Document.id, Revision.revision_number == latest_number),
        )
        .outerjoin(RevisionText, RevisionText.revision_id == Revision.id)
        .outerjoin(Artifact, Artifact.id == RevisionText.source_artifact_id)
        .outerjoin(selected_job, selected_job.id == RevisionText.processing_job_id)
        .outerjoin(latest_job, latest_job.id == latest_job_id)
        .order_by(Document.created_at.desc(), Document.id)
    )


def classify(row, request: SearchRequest) -> SearchResult:
    warnings = list(row["quality_warnings"] or [])
    has_text = row["processing_job_id"] is not None
    supported = request.mode == "exact" or row["normalization_version"] == NORMALIZATION_VERSION
    if row["revision_id"] is None:
        warnings.append("no_revision")
    if not has_text:
        warnings.append("no_selected_text")
    else:
        if not supported:
            warnings.append("unsupported_normalization_version")
        if row["coverage"] != "complete":
            warnings.append("incomplete_extraction")
        if row["quality_status"] != "no_known_issue":
            warnings.append(
                "extraction_needs_review"
                if row["quality_status"] == "needs_review"
                else "quality_unassessed"
            )
        if row["manual_review"]:
            warnings.append("manual_review_requested")
    latest = None
    if row["latest_job_id"]:
        latest = SearchJobOut(
            id=row["latest_job_id"],
            status=row["latest_job_status"],
            error_message=row["latest_job_error"],
        )
        if latest.id != row["processing_job_id"]:
            if latest.status == "failed":
                warnings.append("newer_run_failed" if has_text else "processing_failed")
            elif latest.status in {"queued", "running"}:
                warnings.append("newer_run_pending" if has_text else "processing_pending")
    position = row["position"] or 0
    if has_text and supported and position > 0:
        status = "found"
    elif (
        has_text
        and supported
        and row["coverage"] == "complete"
        and row["quality_status"] == "no_known_issue"
        and not row["manual_review"]
    ):
        status = "not_found_in_processed_text"
    else:
        status = "unverifiable"
    return SearchResult(
        document_id=row["document_id"],
        title=row["title"],
        revision_id=row["revision_id"],
        revision_number=row["revision_number"],
        artifact_id=row["source_artifact_id"],
        processing_job_id=row["processing_job_id"],
        normalization_version=row["normalization_version"],
        processor_versions=row["processor_versions"],
        mode=request.mode,
        status=status,
        coverage=row["coverage"],
        quality_status=row["quality_status"],
        pages_total=row["pages_total"],
        pages_processed=row["pages_processed"],
        pages_failed=row["pages_failed"],
        warnings=sorted(set(warnings)),
        latest_job=latest,
        start_offset=position - 1 if status == "found" else None,
        offset_basis="normalized_text" if request.mode == "normalized" else "plain_text",
    )


def add_evidence(
    session: Session, results: list[SearchResult], phrase: str, column, mode: str
) -> None:
    if not results:
        return
    ids = [result.revision_id for result in results]
    position = func.strpos(column, phrase)
    snippet_start = func.greatest(position - 80, 1)
    snippets = {
        row.revision_id: row
        for row in session.execute(
            select(
                RevisionText.revision_id,
                (snippet_start - 1).label("snippet_start"),
                func.substr(column, snippet_start, len(phrase) + 160).label("snippet"),
            ).where(RevisionText.revision_id.in_(ids))
        )
    }
    pages = defaultdict(list)
    for row in session.execute(
        select(
            PageText.revision_id,
            PageText.page_number,
            PageText.start_offset,
            PageText.end_offset,
            func.char_length(PageText.text).label("raw_length"),
        )
        .where(PageText.revision_id.in_(ids))
        .order_by(PageText.revision_id, PageText.page_number)
    ):
        pages[row.revision_id].append(row)
    for result in results:
        result.matched_text = phrase
        result.end_offset = result.start_offset + len(phrase)
        snippet = snippets[result.revision_id]
        result.snippet, result.snippet_start_offset = snippet.snippet, snippet.snippet_start
        raw_start = 0
        for page in pages[result.revision_id]:
            start, end = (
                (page.start_offset, page.end_offset)
                if mode == "normalized"
                else (raw_start, raw_start + page.raw_length)
            )
            if start < result.end_offset and end > result.start_offset:
                result.page_numbers.append(page.page_number)
            raw_start += page.raw_length + len("\n\f\n")
        if result.page_numbers:
            result.page_number = result.page_numbers[0]
            result.end_page_number = result.page_numbers[-1]
        else:
            result.warnings.append("page_location_unavailable")

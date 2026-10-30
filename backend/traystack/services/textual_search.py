import hashlib
from datetime import UTC, datetime
from importlib.metadata import version

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from traystack.models import Document, PageText, RevisionText
from traystack.search_schemas import SearchRequest
from traystack.services.normalization import NORMALIZATION_VERSION, normalize_for_search
from traystack.services.search import classify, selected_scope
from traystack.services.textual_matching import (
    CANDIDATE_POLICY,
    SCORER_VERSION,
    WorkBudget,
    find_passages,
    text_differences,
)
from traystack.textual_schemas import (
    TextualDocument,
    TextualGroup,
    TextualOccurrence,
    TextualSearchRequest,
    TextualSearchResponse,
    TextualSummary,
)


def textual_snapshot(session: Session, request: TextualSearchRequest) -> TextualSearchResponse:
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    session.execute(text("SET TRANSACTION READ ONLY"))
    searched_at = datetime.now(UTC)
    phrase = normalize_for_search(request.query) if request.mode == "normalized" else request.query
    column = (
        RevisionText.normalized_text if request.mode == "normalized" else RevisionText.plain_text
    )
    statement = selected_scope(phrase, column).add_columns(column.label("search_text"))
    if request.document_id is not None:
        statement = statement.where(Document.id == request.document_id)
    legacy_request = SearchRequest(query=request.query, mode=request.mode)
    budget = WorkBudget()
    matches, unsearchable = [], []
    documents_total = searched = 0
    for row in session.execute(statement.execution_options(yield_per=10)).mappings():
        documents_total += 1
        provenance = classify(row, legacy_request)
        document = TextualDocument.model_validate(provenance.model_dump())
        content = row["search_text"]
        supported = request.mode == "exact" or row["normalization_version"] == NORMALIZATION_VERSION
        if not content or not content.strip() or not supported:
            unsearchable.append(document)
            continue
        searched += 1
        passages = find_passages(content, phrase, request.minimum_score, budget)
        if passages:
            matches.append((document, content, passages))
    # Stable ties retain the scope's document recency/ID ordering.
    matches.sort(key=lambda item: -item[2][0].score)
    groups = []
    for document, content, passages in matches[request.offset : request.offset + request.limit]:
        pages = session.scalars(
            select(PageText)
            .where(PageText.revision_id == document.revision_id)
            .order_by(PageText.page_number)
        ).all()
        occurrences = []
        for candidate in passages[
            request.occurrence_offset : request.occurrence_offset + request.occurrence_limit
        ]:
            numbers, logical, raw_start = [], False, 0
            for page in pages:
                start, end = (
                    (page.start_offset, page.end_offset)
                    if request.mode == "normalized"
                    else (raw_start, raw_start + len(page.text))
                )
                if start < end and start < candidate.end and end > candidate.start:
                    numbers.append(page.page_number)
                    logical |= page.extraction_method in {"plain_text", "html_text"}
                raw_start += len(page.text) + len("\n\f\n")
            snippet_start = max(0, candidate.start - 100)
            matched = content[candidate.start : candidate.end]
            occurrence_id = hashlib.sha256(
                f"{document.processing_job_id}|{request.mode}|{SCORER_VERSION}|{CANDIDATE_POLICY}|"
                f"{phrase}|{candidate.start}|{candidate.end}".encode()
            ).hexdigest()
            occurrences.append(
                TextualOccurrence(
                    occurrence_id=occurrence_id,
                    score=round(candidate.score, 4),
                    start_offset=candidate.start,
                    end_offset=candidate.end,
                    matched_text=matched,
                    snippet=content[snippet_start : candidate.end + 100],
                    snippet_start_offset=snippet_start,
                    page_numbers=numbers,
                    page_reference="logical"
                    if logical
                    else ("physical" if numbers else "unavailable"),
                    differences=text_differences(phrase, matched),
                )
            )
        groups.append(
            TextualGroup(
                document=document,
                occurrences=occurrences,
                occurrence_total=len(passages),
                occurrence_limit=request.occurrence_limit,
                occurrence_offset=request.occurrence_offset,
            )
        )
    warnings = []
    if request.minimum_score == 0:
        warnings.append("text_filter_disabled")
    elif request.minimum_score < 70:
        warnings.append("low_text_threshold")
    if len(phrase) < 8:
        warnings.append("short_query")
    return TextualSearchResponse(
        query=request.query,
        effective_query=phrase,
        mode=request.mode,
        minimum_score=request.minimum_score,
        searched_at=searched_at,
        scorer_version=SCORER_VERSION,
        scorer_library_version=version("rapidfuzz"),
        candidate_policy=CANDIDATE_POLICY,
        offset_basis="normalized_text" if request.mode == "normalized" else "plain_text",
        warnings=warnings,
        summary=TextualSummary(
            documents_total=documents_total,
            documents_searched=searched,
            documents_with_matches=len(matches),
            documents_without_matches=searched - len(matches),
            documents_unsearchable=len(unsearchable),
            occurrences_total=sum(len(item[2]) for item in matches),
        ),
        results=groups,
        total=len(matches),
        limit=request.limit,
        offset=request.offset,
        unsearchable=unsearchable[
            request.unsearchable_offset : request.unsearchable_offset + request.unsearchable_limit
        ],
        unsearchable_total=len(unsearchable),
        unsearchable_limit=request.unsearchable_limit,
        unsearchable_offset=request.unsearchable_offset,
    )

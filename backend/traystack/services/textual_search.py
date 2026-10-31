from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from traystack.models import Document, PageText, PassageReview, RevisionText
from traystack.review_schemas import ReviewCounts, ReviewOut
from traystack.search_schemas import SearchRequest
from traystack.services.normalization import NORMALIZATION_VERSION
from traystack.services.passage_identity import occurrence_identity, text_fingerprint
from traystack.services.query_guidance import assess_query
from traystack.services.search import classify, selected_scope
from traystack.services.textual_matching import (
    CANDIDATE_POLICY,
    SCORER_VERSION,
    PassageBudget,
    SearchTooBroad,
    WorkBudget,
    find_passages,
    text_differences,
)
from traystack.textual_schemas import (
    QueryNotice,
    TextualDocument,
    TextualGroup,
    TextualOccurrence,
    TextualSearchRequest,
    TextualSearchResponse,
    TextualSummary,
)


def textual_snapshot(
    session: Session, request: TextualSearchRequest, semantic_provider=None, capture=None
) -> TextualSearchResponse:
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    session.execute(text("SET TRANSACTION READ ONLY"))
    searched_at = datetime.now(UTC)
    assessment = assess_query(request)
    phrase = assessment.effective_query
    column = (
        RevisionText.normalized_text if request.mode == "normalized" else RevisionText.plain_text
    )
    statement = selected_scope(phrase, column).add_columns(column.label("search_text"))
    if request.document_id is not None:
        statement = statement.where(Document.id == request.document_id)
    legacy_request = SearchRequest(query=request.query, mode=request.mode)
    budget = WorkBudget()
    passage_budget = PassageBudget()
    matches, unsearchable = [], []
    documents_total = searched = 0
    for row in session.execute(statement.execution_options(yield_per=10)).mappings():
        documents_total += 1
        provenance = classify(row, legacy_request)
        document = TextualDocument.model_validate(provenance.model_dump())
        content = row["search_text"]
        supported = request.mode == "exact" or row["normalization_version"] == NORMALIZATION_VERSION
        searchable = bool(content and content.strip() and supported)
        if capture is not None:
            capture.add_scope(document, searchable)
        if not searchable:
            unsearchable.append(document)
            continue
        searched += 1
        try:
            passages = find_passages(content, phrase, request.minimum_score, budget, passage_budget)
        except SearchTooBroad as error:
            error.documents_inspected = documents_total
            raise
        if passages:
            matches.append((document, content, passages))
    textual_candidates_total = passage_budget.total
    semantic_values, semantic = {}, None
    if request.minimum_semantic_score is not None:
        if textual_candidates_total > 500:
            error = SearchTooBroad(
                "Too many passages for semantic comparison. Raise the textual threshold or "
                "narrow the document selection.",
                reason="semantic_passage_limit",
                resource="semantic_passages",
                limit=500,
                observed=textual_candidates_total,
            )
            error.documents_inspected = documents_total
            raise error
        engine = semantic_provider()
        semantic = engine.provenance()
        flat = [
            (document, content, candidate)
            for document, content, passages in matches
            for candidate in passages
        ]
        try:
            values = engine.compare(phrase, [content[c.start : c.end] for _, content, c in flat])
        except SearchTooBroad as error:
            error.documents_inspected = documents_total
            raise
        for (document, _, candidate), value in zip(flat, values, strict=True):
            semantic_values[document.document_id, candidate.start, candidate.end] = value
        filtered = []
        for document, content, passages in matches:
            retained = [
                candidate
                for candidate in passages
                if semantic_values[document.document_id, candidate.start, candidate.end][0]
                >= request.minimum_semantic_score
            ]
            if retained:
                filtered.append((document, content, retained))
        matches = filtered
    jobs = [document.processing_job_id for document, _, _ in matches]
    reviews = (
        {
            item.occurrence_id: item
            for item in session.scalars(
                select(PassageReview).where(
                    PassageReview.processing_job_id.in_(jobs),
                    PassageReview.effective_query == phrase,
                    PassageReview.mode == request.mode,
                    PassageReview.scorer_version == SCORER_VERSION,
                    PassageReview.candidate_policy == CANDIDATE_POLICY,
                )
            )
        }
        if jobs
        else {}
    )
    review_counts = Counter()
    document_review_counts = {}
    review_matches = []
    for document, content, passages in matches:
        retained = []
        document_counts = Counter()
        for candidate in passages:
            identity = occurrence_identity(
                document.processing_job_id, request.mode, phrase, candidate.start, candidate.end
            )
            review = reviews.get(identity)
            if review is not None and (
                review.matched_sha256 != text_fingerprint(content[candidate.start : candidate.end])
                or review.source_artifact_id != document.artifact_id
                or review.normalization_version != document.normalization_version
            ):
                reviews.pop(identity)
                review = None
            decision = review.decision if review is not None else "unreviewed"
            review_counts[decision] += 1
            document_counts[decision] += 1
            if request.review_filter == "all" or request.review_filter == decision:
                retained.append(candidate)
        document_review_counts[document.document_id] = ReviewCounts(**document_counts)
        if retained:
            review_matches.append((document, content, retained))
    matches = review_matches
    # Stable ties retain the scope's document recency/ID ordering.
    matches.sort(key=lambda item: -item[2][0].score)
    groups = []
    visible_matches = (
        matches if capture is not None else matches[request.offset : request.offset + request.limit]
    )
    for document, content, passages in visible_matches:
        pages = session.scalars(
            select(PageText)
            .where(PageText.revision_id == document.revision_id)
            .order_by(PageText.page_number)
        ).all()
        if capture is not None:
            capture.add_source(session.get(RevisionText, document.revision_id), pages)
        occurrences = []
        visible_passages = (
            passages
            if capture is not None
            else passages[
                request.occurrence_offset : request.occurrence_offset + request.occurrence_limit
            ]
        )
        for candidate in visible_passages:
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
            occurrence_id = occurrence_identity(
                document.processing_job_id, request.mode, phrase, candidate.start, candidate.end
            )
            occurrences.append(
                TextualOccurrence(
                    occurrence_id=occurrence_id,
                    score=round(candidate.score, 4),
                    matched_sha256=text_fingerprint(matched),
                    review=(
                        ReviewOut.model_validate(reviews[occurrence_id])
                        if occurrence_id in reviews
                        else ReviewOut()
                    ),
                    semantic_score=(
                        round(
                            semantic_values[document.document_id, candidate.start, candidate.end][
                                0
                            ],
                            4,
                        )
                        if semantic is not None
                        else None
                    ),
                    semantic_cosine=(
                        semantic_values[document.document_id, candidate.start, candidate.end][1]
                        if semantic is not None
                        else None
                    ),
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
                review_counts=document_review_counts[document.document_id],
                document=document,
                occurrences=occurrences,
                occurrence_total=len(passages),
                occurrence_limit=request.occurrence_limit,
                occurrence_offset=request.occurrence_offset,
            )
        )
    result_warnings = []
    if passage_budget.total >= 500 or passage_budget.peak_document_count >= 50:
        result_warnings.append(
            QueryNotice(
                code="many_passages",
                message=(
                    f"The textual stage found {passage_budget.total} candidate passages. "
                    "Consider a higher threshold or a narrower selection to reduce review work."
                ),
            )
        )
    if request.minimum_semantic_score is not None:
        result_warnings.append(
            QueryNotice(
                code="semantic_not_equivalence",
                message="Semantic scores measure model similarity, not confidence or legal "
                "equivalence. Negations, names and amounts can change meaning despite "
                "a high score.",
            )
        )
        if request.minimum_semantic_score == 100 and request.minimum_score < 100:
            result_warnings.append(
                QueryNotice(
                    code="semantic_exact_only",
                    message="Semantic 100 retains only identical "
                    "comparison text. A textual threshold of 100 is sufficient for this purpose.",
                )
            )
        elif request.minimum_semantic_score < 50:
            result_warnings.append(
                QueryNotice(
                    code="permissive_semantic_threshold",
                    message="This semantic threshold is "
                    "permissive and can retain unrelated wording. Zero applies no semantic filter.",
                )
            )
    warnings = [notice.code for notice in [*assessment.warnings, *result_warnings]]
    return TextualSearchResponse(
        review_filter=request.review_filter,
        review_counts=ReviewCounts(**review_counts),
        query=request.query,
        effective_query=phrase,
        mode=request.mode,
        minimum_score=request.minimum_score,
        document_id=request.document_id,
        searched_at=searched_at,
        minimum_semantic_score=request.minimum_semantic_score,
        semantic=semantic,
        textual_candidates_total=textual_candidates_total,
        scorer_version=SCORER_VERSION,
        scorer_library_version=version("rapidfuzz"),
        candidate_policy=CANDIDATE_POLICY,
        offset_basis="normalized_text" if request.mode == "normalized" else "plain_text",
        warnings=warnings,
        assessment=assessment,
        result_warnings=result_warnings,
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
        unsearchable=(
            unsearchable
            if capture is not None
            else unsearchable[
                request.unsearchable_offset : request.unsearchable_offset
                + request.unsearchable_limit
            ]
        ),
        unsearchable_total=len(unsearchable),
        unsearchable_limit=request.unsearchable_limit,
        unsearchable_offset=request.unsearchable_offset,
    )

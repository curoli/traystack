import hashlib
from datetime import UTC, datetime
from importlib.metadata import version

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from traystack.models import Document, PageText, RevisionText
from traystack.search_schemas import SearchRequest
from traystack.services.normalization import NORMALIZATION_VERSION
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
    session: Session, request: TextualSearchRequest, semantic_provider=None
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
        if not content or not content.strip() or not supported:
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
        unsearchable=unsearchable[
            request.unsearchable_offset : request.unsearchable_offset + request.unsearchable_limit
        ],
        unsearchable_total=len(unsearchable),
        unsearchable_limit=request.unsearchable_limit,
        unsearchable_offset=request.unsearchable_offset,
    )

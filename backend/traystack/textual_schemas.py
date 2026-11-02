from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from traystack.review_schemas import ReviewCounts, ReviewFilter, ReviewOut
from traystack.search_schemas import SearchJobOut, SearchRequest


class TextualAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    mode: Literal["exact", "normalized"] = "normalized"
    minimum_score: float = Field(default=85, gt=0, le=100, allow_inf_nan=False)

    @field_validator("query")
    @classmethod
    def valid_query(cls, value):
        return SearchRequest.valid_query(value)


class TextualSearchRequest(TextualAssessmentRequest):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    uncategorized: bool = False
    auto_confirm_textual: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    auto_confirm_semantic: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    ready_only: bool = False
    review_filter: ReviewFilter = "all"
    minimum_semantic_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    scope: Literal["latest"] = "latest"
    document_id: UUID | None = None
    limit: int = Field(default=10, ge=1, le=25)
    offset: int = Field(default=0, ge=0)
    occurrence_limit: int = Field(default=5, ge=1, le=25)
    occurrence_offset: int = Field(default=0, ge=0)
    unsearchable_limit: int = Field(default=10, ge=1, le=100)
    unsearchable_offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def occurrence_paging(self):
        if self.category and self.uncategorized:
            raise ValueError("Choose a category or uncategorized documents")
        if (self.auto_confirm_textual is None) != (self.auto_confirm_semantic is None):
            raise ValueError("Both auto-confirm thresholds must be set together")
        if self.auto_confirm_textual is not None and self.minimum_semantic_score is None:
            raise ValueError("Auto-confirm requires semantic scores")
        if self.occurrence_offset and self.document_id is None:
            raise ValueError("Occurrence paging requires document_id")
        return self


class TextualDocument(BaseModel):
    category: str | None = None
    document_id: UUID
    title: str
    revision_id: UUID | None
    revision_number: int | None
    artifact_id: UUID | None
    processing_job_id: UUID | None
    normalization_version: str | None
    processor_versions: dict[str, Any] | None
    coverage: str | None
    quality_status: str | None
    pages_total: int | None
    pages_processed: int | None
    pages_failed: int | None
    warnings: list[str]
    latest_job: SearchJobOut | None


class TextDifference(BaseModel):
    kind: Literal["equal", "replace", "insert", "delete"]
    query_text: str
    passage_text: str


class TextualOccurrence(BaseModel):
    raw_textual_score: float | None = None
    raw_semantic_score: float | None = None
    auto_confirmed: bool = False
    occurrence_id: str
    score: float
    matched_sha256: str
    review_at_capture: ReviewOut | None = None
    review: ReviewOut = Field(default_factory=ReviewOut)
    semantic_score: float | None = None
    semantic_cosine: float | None = None
    start_offset: int
    end_offset: int
    matched_text: str
    snippet: str
    snippet_start_offset: int
    page_numbers: list[int]
    page_reference: Literal["physical", "logical", "unavailable"]
    differences: list[TextDifference]


class TextualGroup(BaseModel):
    review_counts: ReviewCounts
    document: TextualDocument
    occurrence_total: int
    occurrence_limit: int
    occurrence_offset: int
    occurrences: list[TextualOccurrence]


class TextualSummary(BaseModel):
    documents_total: int
    documents_searched: int
    documents_with_matches: int
    documents_without_matches: int
    documents_unsearchable: int
    occurrences_total: int


class QueryNotice(BaseModel):
    code: str
    message: str


class TextualAssessment(BaseModel):
    policy_version: str
    effective_query: str
    comparison_characters: int
    content_characters: int
    word_count: int
    equal_length_edit_budget: int
    warnings: list[QueryNotice]


class SemanticProvenance(BaseModel):
    model: str
    pipeline: str
    score_version: str
    max_tokens: int


class DocumentOutcome(BaseModel):
    document: TextualDocument
    state: Literal["confirmed", "unreviewed", "no_active_match"]


class TextualSearchResponse(BaseModel):
    review_scope: Literal["shared", "run"] = "shared"
    document_outcomes: list[DocumentOutcome] = Field(default_factory=list)
    category: str | None = None
    uncategorized: bool = False
    auto_confirm_textual: float | None = None
    auto_confirm_semantic: float | None = None
    captured_review_filter: ReviewFilter | None = None
    run_id: UUID | None = None
    run_name: str | None = None
    parent_run_id: UUID | None = None
    scope_total: int | None = None
    review_filter: ReviewFilter = "all"
    review_counts: ReviewCounts
    query: str
    effective_query: str
    mode: Literal["exact", "normalized"]
    minimum_score: float
    scope: Literal["latest"] = "latest"
    document_id: UUID | None = None
    searched_at: datetime
    minimum_semantic_score: float | None = None
    semantic: SemanticProvenance | None = None
    textual_candidates_total: int
    scorer_version: str
    scorer_library_version: str
    candidate_policy: str
    offset_basis: Literal["plain_text", "normalized_text"]
    warnings: list[str]
    assessment: TextualAssessment
    result_warnings: list[QueryNotice]
    summary: TextualSummary
    results: list[TextualGroup]
    total: int
    limit: int
    offset: int
    unsearchable: list[TextualDocument]
    unsearchable_total: int
    unsearchable_limit: int
    unsearchable_offset: int

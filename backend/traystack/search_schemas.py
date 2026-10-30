from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SearchStatus = Literal["found", "not_found_in_processed_text", "unverifiable"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["exact", "normalized"] = "normalized"
    relation: Literal["contains", "lacks"] = "contains"
    scope: Literal["latest"] = "latest"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    unverifiable_limit: int = Field(default=25, ge=1, le=100)
    unverifiable_offset: int = Field(default=0, ge=0)

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Query must contain text and cannot contain null characters")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Query contains invalid Unicode") from None
        return value  # Exact search preserves the user's whitespace and case.


class SearchJobOut(BaseModel):
    id: UUID
    status: str
    error_message: str | None


class SearchResult(BaseModel):
    document_id: UUID
    title: str
    revision_id: UUID | None
    revision_number: int | None
    artifact_id: UUID | None
    processing_job_id: UUID | None
    normalization_version: str | None
    processor_versions: dict[str, Any] | None
    mode: Literal["exact", "normalized"]
    status: SearchStatus
    coverage: str | None
    quality_status: str | None
    pages_total: int | None
    pages_processed: int | None
    pages_failed: int | None
    warnings: list[str]
    latest_job: SearchJobOut | None
    matched_text: str | None = None
    snippet: str | None = None
    snippet_start_offset: int | None = None
    page_number: int | None = None
    end_page_number: int | None = None
    page_numbers: list[int] = Field(default_factory=list)
    start_offset: int | None = None
    end_offset: int | None = None
    offset_basis: Literal["plain_text", "normalized_text"]
    score: None = None


class SearchSummary(BaseModel):
    documents_total: int
    found: int
    not_found_in_processed_text: int
    unverifiable: int


class SearchResponse(BaseModel):
    query: str
    effective_query: str
    mode: Literal["exact", "normalized"]
    relation: Literal["contains", "lacks"]
    scope: Literal["latest"]
    searched_at: datetime
    match_policy: Literal["first_occurrence_per_revision"] = "first_occurrence_per_revision"
    summary: SearchSummary
    results: list[SearchResult]
    total: int
    limit: int
    offset: int
    unverifiable: list[SearchResult]
    unverifiable_total: int
    unverifiable_limit: int
    unverifiable_offset: int

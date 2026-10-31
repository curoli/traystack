from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from traystack.search_schemas import SearchRequest

ReviewDecision = Literal["unreviewed", "keep", "dismiss", "later"]
ReviewFilter = Literal["all", "unreviewed", "keep", "dismiss", "later"]


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    decision: ReviewDecision = "unreviewed"
    version: int = 0
    updated_at: datetime | None = None


class ReviewCounts(BaseModel):
    unreviewed: int = 0
    keep: int = 0
    dismiss: int = 0
    later: int = 0


class ReviewWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurrence_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_id: UUID
    revision_id: UUID
    processing_job_id: UUID
    source_artifact_id: UUID
    normalization_version: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=500)
    mode: Literal["exact", "normalized"]
    scorer_version: str = Field(min_length=1, max_length=100)
    candidate_policy: str = Field(min_length=1, max_length=150)
    start_offset: int = Field(ge=0, le=20_000_000)
    end_offset: int = Field(gt=0, le=20_000_000)
    matched_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: ReviewDecision
    expected_version: int = Field(ge=0, le=2_000_000_000)

    @field_validator("query")
    @classmethod
    def valid_query(cls, value):
        return SearchRequest.valid_query(value)

    @model_validator(mode="after")
    def offsets(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("Passage end must be after its start")
        return self

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision_id: UUID
    source_artifact_id: UUID | None
    kind: str
    mime_type: str
    original_filename: str | None
    sha256: str
    size_bytes: int
    processor: str | None
    processor_version: str | None
    parameters: dict[str, Any]
    created_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision_id: UUID
    source_artifact_id: UUID
    retry_of_job_id: UUID | None
    operation: str
    status: Literal["queued", "running", "completed", "failed"]
    attempts: int
    parameters: dict[str, Any]
    processor_versions: dict[str, Any]
    normalization_version: str
    error_message: str | None
    result_artifact_ids: list[str]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_artifact_id: UUID | None = None
    requires_manual_review: bool = False


class TextSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    revision_id: UUID
    source_artifact_id: UUID
    processing_job_id: UUID
    normalization_version: str
    status: Literal["complete", "partial", "unavailable"]
    quality_status: Literal["no_known_issue", "needs_review", "unassessed"]
    quality_warnings: list[str]
    pages_total: int
    pages_processed: int
    pages_failed: int
    updated_at: datetime


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    text: str
    normalized_text: str
    start_offset: int
    end_offset: int
    extraction_method: str
    status: str
    quality_status: str
    quality_warnings: list[str]
    confidence: float | None
    layout_metadata: dict[str, Any]


class TextContentOut(TextSummaryOut):
    plain_text: str
    normalized_text: str
    pages: list[PageOut]


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    revision_number: int
    label: str | None
    created_at: datetime
    processing_status: Literal["not_processed", "queued", "running", "completed", "failed"]
    artifacts: list[ArtifactOut]
    jobs: list[JobOut]
    text_index: TextSummaryOut | None


class DocumentOut(BaseModel):
    id: UUID
    title: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    revisions: list[RevisionOut]


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]
    storage: Literal["ok", "unavailable"]
    milestone: int = Field(default=2)

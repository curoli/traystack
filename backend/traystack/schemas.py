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


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    revision_number: int
    label: str | None
    created_at: datetime
    processing_status: Literal["not_processed"] = "not_processed"
    artifacts: list[ArtifactOut]


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
    milestone: int = Field(default=1)

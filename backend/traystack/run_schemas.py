from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from traystack.textual_schemas import TextualSearchRequest


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: TextualSearchRequest
    name: str | None = Field(default=None, max_length=200)
    parent_run_id: UUID | None = None


class RunName(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("A saved search needs a name")
        return value.strip()


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    query: str
    searched_at: datetime
    created_at: datetime
    parent_run_id: UUID | None
    result_documents: int
    result_passages: int

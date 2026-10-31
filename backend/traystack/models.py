import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("length(trim(title)) > 0", name="ck_document_title"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="document", order_by="Revision.revision_number"
    )


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision_number", name="uq_revision_number"),
        CheckConstraint("revision_number > 0", name="ck_revision_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document: Mapped[Document] = relationship(back_populates="revisions")
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="revision",
        foreign_keys="Artifact.revision_id",
        order_by="Artifact.created_at",
    )

    jobs: Mapped[list["ProcessingJob"]] = relationship(
        foreign_keys="ProcessingJob.revision_id",
        order_by="(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())",
    )
    text_index: Mapped["RevisionText | None"] = relationship(
        foreign_keys="RevisionText.revision_id", uselist=False
    )

    @property
    def processing_status(self) -> str:
        return self.jobs[0].status if self.jobs else "not_processed"


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("id", "revision_id", name="uq_artifact_revision"),
        ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_artifact_source_same_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_artifact_sha256"),
        CheckConstraint(
            "source_artifact_id IS NULL OR source_artifact_id <> id", name="ck_no_self_source"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("revisions.id", ondelete="RESTRICT"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(50))
    mime_type: Mapped[str] = mapped_column(String(100))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    processor: Mapped[str | None] = mapped_column(String(100))
    processor_version: Mapped[str | None] = mapped_column(String(100))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[Revision] = relationship(
        back_populates="artifacts", foreign_keys=[revision_id]
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("id", "revision_id", name="uq_job_revision"),
        ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_job_source_same_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["retry_of_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_retry_same_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="ck_job_status"
        ),
        CheckConstraint("operation = 'extract_and_index'", name="ck_job_operation"),
        CheckConstraint("attempts >= 0", name="ck_job_attempts"),
        Index("ix_processing_jobs_queue", "status", "created_at", "id"),
        Index(
            "uq_active_job_per_revision",
            "revision_id",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("revisions.id", ondelete="RESTRICT"), index=True
    )
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    retry_of_job_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    operation: Mapped[str] = mapped_column(String(50), default="extract_and_index")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    processor_versions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    normalization_version: Mapped[str] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(String(200))
    result_artifact_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RevisionText(Base):
    __tablename__ = "revision_texts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_text_source_same_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_text_job_same_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('complete','partial','unavailable')", name="ck_text_status"),
        CheckConstraint(
            "quality_status IN ('no_known_issue','needs_review','unassessed')",
            name="ck_text_quality",
        ),
        CheckConstraint(
            "pages_total > 0 AND pages_processed >= 0 AND pages_failed >= 0 "
            "AND pages_total = pages_processed + pages_failed",
            name="ck_text_page_counts",
        ),
    )

    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("revisions.id", ondelete="RESTRICT"), primary_key=True
    )
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    processing_job_id: Mapped[uuid.UUID] = mapped_column(index=True)
    normalization_version: Mapped[str] = mapped_column(String(100))
    plain_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    quality_status: Mapped[str] = mapped_column(String(30))
    quality_warnings: Mapped[list[str]] = mapped_column(JSONB)
    pages_total: Mapped[int] = mapped_column(Integer)
    pages_processed: Mapped[int] = mapped_column(Integer)
    pages_failed: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    pages: Mapped[list["PageText"]] = relationship(order_by="PageText.page_number")


class PageText(Base):
    __tablename__ = "page_texts"
    __table_args__ = (
        UniqueConstraint("revision_id", "page_number", name="uq_page_number"),
        CheckConstraint("page_number > 0", name="ck_page_number"),
        CheckConstraint("start_offset >= 0 AND end_offset >= start_offset", name="ck_page_offsets"),
        CheckConstraint("status IN ('complete','partial','unavailable')", name="ck_page_status"),
        CheckConstraint(
            "quality_status IN ('no_known_issue','needs_review','unassessed')",
            name="ck_page_quality",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_page_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("revision_texts.revision_id", ondelete="CASCADE"), index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    quality_status: Mapped[str] = mapped_column(String(30))
    quality_warnings: Mapped[list[str]] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    layout_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PassageReview(Base):
    __tablename__ = "passage_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_review_job_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_review_source_revision",
            ondelete="RESTRICT",
        ),
        CheckConstraint("occurrence_id ~ '^[0-9a-f]{64}$'", name="ck_review_identity"),
        CheckConstraint("matched_sha256 ~ '^[0-9a-f]{64}$'", name="ck_review_hash"),
        CheckConstraint("mode IN ('exact','normalized')", name="ck_review_mode"),
        CheckConstraint(
            "decision IN ('unreviewed','keep','dismiss','later')", name="ck_review_decision"
        ),
        CheckConstraint("version > 0", name="ck_review_version"),
        CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_review_offsets"
        ),
        Index("ix_passage_reviews_query", "processing_job_id", "mode"),
    )

    occurrence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("revisions.id", ondelete="RESTRICT"))
    processing_job_id: Mapped[uuid.UUID] = mapped_column()
    source_artifact_id: Mapped[uuid.UUID] = mapped_column()
    normalization_version: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))
    effective_query: Mapped[str] = mapped_column(Text)
    scorer_version: Mapped[str] = mapped_column(String(100))
    candidate_policy: Mapped[str] = mapped_column(String(150))
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    matched_sha256: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SearchRun(Base):
    __tablename__ = "search_runs"
    __table_args__ = (
        CheckConstraint("snapshot_version = 1", name="ck_search_run_version"),
        CheckConstraint("length(trim(name)) > 0", name="ck_search_run_name"),
        CheckConstraint(
            "result_documents >= 0 AND result_passages >= 0", name="ck_search_run_counts"
        ),
        Index("ix_search_runs_created", "created_at", "id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(Text)
    parent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_runs.id", ondelete="RESTRICT")
    )
    snapshot_version: Mapped[int] = mapped_column(Integer, default=1)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scope_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    result_documents: Mapped[int] = mapped_column(Integer)
    result_passages: Mapped[int] = mapped_column(Integer)
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArchivedText(Base):
    __tablename__ = "archived_texts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_archived_text_job_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_archived_text_source_revision",
            ondelete="RESTRICT",
        ),
    )
    processing_job_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("revisions.id", ondelete="RESTRICT"))
    source_artifact_id: Mapped[uuid.UUID] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sha256: Mapped[str] = mapped_column(String(64))


class SearchRunSource(Base):
    __tablename__ = "search_run_sources"
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_runs.id", ondelete="RESTRICT"), primary_key=True
    )
    processing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("archived_texts.processing_job_id", ondelete="RESTRICT"), primary_key=True
    )

"""Processing runs and selected page text

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("retry_of_job_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "processor_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("normalization_version", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.String(length=200), nullable=True),
        sa.Column(
            "result_artifact_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("operation = 'extract_and_index'", name="ck_job_operation"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')", name="ck_job_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_job_attempts"),
        sa.ForeignKeyConstraint(
            ["retry_of_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_retry_same_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_job_source_same_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "revision_id", name="uq_job_revision"),
    )
    op.create_index(
        op.f("ix_processing_jobs_retry_of_job_id"),
        "processing_jobs",
        ["retry_of_job_id"],
        unique=False,
    )
    op.create_index("ix_processing_jobs_queue", "processing_jobs", ["status", "created_at", "id"])
    op.create_index(
        op.f("ix_processing_jobs_revision_id"), "processing_jobs", ["revision_id"], unique=False
    )
    op.create_index(
        op.f("ix_processing_jobs_source_artifact_id"),
        "processing_jobs",
        ["source_artifact_id"],
        unique=False,
    )
    op.create_index(
        "uq_active_job_per_revision",
        "processing_jobs",
        ["revision_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "revision_texts",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("processing_job_id", sa.Uuid(), nullable=False),
        sa.Column("normalization_version", sa.String(length=100), nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("quality_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pages_total", sa.Integer(), nullable=False),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("pages_failed", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quality_status IN ('no_known_issue','needs_review','unassessed')",
            name="ck_text_quality",
        ),
        sa.CheckConstraint("status IN ('complete','partial','unavailable')", name="ck_text_status"),
        sa.CheckConstraint(
            "pages_total > 0 AND pages_processed >= 0 AND pages_failed >= 0 "
            "AND pages_total = pages_processed + pages_failed",
            name="ck_text_page_counts",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_text_job_same_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_text_source_same_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index(
        op.f("ix_revision_texts_processing_job_id"),
        "revision_texts",
        ["processing_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_revision_texts_source_artifact_id"),
        "revision_texts",
        ["source_artifact_id"],
        unique=False,
    )
    op.create_table(
        "page_texts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quality_status", sa.String(length=30), nullable=False),
        sa.Column("quality_warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("layout_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "quality_status IN ('no_known_issue','needs_review','unassessed')",
            name="ck_page_quality",
        ),
        sa.CheckConstraint("status IN ('complete','partial','unavailable')", name="ck_page_status"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_page_confidence",
        ),
        sa.CheckConstraint("page_number > 0", name="ck_page_number"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset >= start_offset", name="ck_page_offsets"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["revision_texts.revision_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "page_number", name="uq_page_number"),
    )
    op.create_index(op.f("ix_page_texts_revision_id"), "page_texts", ["revision_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_page_texts_revision_id"), table_name="page_texts")
    op.drop_table("page_texts")
    op.drop_index(op.f("ix_revision_texts_source_artifact_id"), table_name="revision_texts")
    op.drop_index(op.f("ix_revision_texts_processing_job_id"), table_name="revision_texts")
    op.drop_table("revision_texts")
    op.drop_index(
        "uq_active_job_per_revision",
        table_name="processing_jobs",
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.drop_index(op.f("ix_processing_jobs_source_artifact_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_revision_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_retry_of_job_id"), table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_queue", table_name="processing_jobs")
    op.drop_table("processing_jobs")

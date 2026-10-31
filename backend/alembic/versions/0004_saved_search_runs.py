"""saved search runs and historical source text

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("parent_run_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("result_documents", sa.Integer(), nullable=False),
        sa.Column("result_passages", sa.Integer(), nullable=False),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_search_run_name"),
        sa.CheckConstraint(
            "result_documents >= 0 AND result_passages >= 0", name="ck_search_run_counts"
        ),
        sa.CheckConstraint("snapshot_version = 1", name="ck_search_run_version"),
        sa.ForeignKeyConstraint(["parent_run_id"], ["search_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_runs_created", "search_runs", ["created_at", "id"], unique=False)
    op.create_table(
        "archived_texts",
        sa.Column("processing_job_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_archived_text_job_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_archived_text_source_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("processing_job_id"),
    )
    op.create_table(
        "search_run_sources",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("processing_job_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["processing_job_id"], ["archived_texts.processing_job_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["search_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("run_id", "processing_job_id"),
    )


def downgrade():
    op.drop_table("search_run_sources")
    op.drop_table("archived_texts")
    op.drop_index("ix_search_runs_created", table_name="search_runs")
    op.drop_table("search_runs")

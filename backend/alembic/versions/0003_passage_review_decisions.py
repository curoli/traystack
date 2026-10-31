"""passage review decisions

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "passage_reviews",
        sa.Column("occurrence_id", sa.String(length=64), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("processing_job_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("normalization_version", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("effective_query", sa.Text(), nullable=False),
        sa.Column("scorer_version", sa.String(length=100), nullable=False),
        sa.Column("candidate_policy", sa.String(length=150), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("matched_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('unreviewed','keep','dismiss','later')", name="ck_review_decision"
        ),
        sa.CheckConstraint("matched_sha256 ~ '^[0-9a-f]{64}$'", name="ck_review_hash"),
        sa.CheckConstraint("mode IN ('exact','normalized')", name="ck_review_mode"),
        sa.CheckConstraint("occurrence_id ~ '^[0-9a-f]{64}$'", name="ck_review_identity"),
        sa.CheckConstraint(
            "start_offset >= 0 AND end_offset > start_offset", name="ck_review_offsets"
        ),
        sa.CheckConstraint("version > 0", name="ck_review_version"),
        sa.ForeignKeyConstraint(
            ["processing_job_id", "revision_id"],
            ["processing_jobs.id", "processing_jobs.revision_id"],
            name="fk_review_job_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_review_source_revision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("occurrence_id"),
    )
    op.create_index(
        "ix_passage_reviews_query", "passage_reviews", ["processing_job_id", "mode"], unique=False
    )


def downgrade():
    op.drop_index("ix_passage_reviews_query", table_name="passage_reviews")
    op.drop_table("passage_reviews")

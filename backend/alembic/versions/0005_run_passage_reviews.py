"""Independent decisions for new saved searches.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "run_passage_reviews",
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("search_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("occurrence_id", sa.String(64), primary_key=True),
        sa.Column("matched_sha256", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "decision IN ('unreviewed','keep','dismiss','later')", name="ck_run_review_decision"
        ),
        sa.CheckConstraint("version > 0", name="ck_run_review_version"),
        sa.CheckConstraint("occurrence_id ~ '^[0-9a-f]{64}$'", name="ck_run_review_identity"),
        sa.CheckConstraint("matched_sha256 ~ '^[0-9a-f]{64}$'", name="ck_run_review_hash"),
    )


def downgrade():
    op.drop_table("run_passage_reviews")

"""Documents, revisions and immutable artifact metadata.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_document_title"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision_number > 0", name="ck_revision_positive"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "revision_number", name="uq_revision_number"),
    )
    op.create_index("ix_revisions_document_id", "revisions", ["document_id"])
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_artifact_id", sa.Uuid()),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("storage_key", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("processor", sa.String(100)),
        sa.Column("processor_version", sa.String(100)),
        sa.Column("parameters", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "revision_id", name="uq_artifact_revision"),
        sa.ForeignKeyConstraint(["revision_id"], ["revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_artifact_id", "revision_id"],
            ["artifacts.id", "artifacts.revision_id"],
            name="fk_artifact_source_same_revision",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_artifact_sha256"),
        sa.CheckConstraint(
            "source_artifact_id IS NULL OR source_artifact_id <> id", name="ck_no_self_source"
        ),
    )
    op.create_index("ix_artifacts_revision_id", "artifacts", ["revision_id"])
    op.create_index("ix_artifacts_source_artifact_id", "artifacts", ["source_artifact_id"])


def downgrade():
    op.drop_table("artifacts")
    op.drop_table("revisions")
    op.drop_table("documents")

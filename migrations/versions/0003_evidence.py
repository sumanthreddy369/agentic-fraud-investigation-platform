"""Immutable case-scoped evidence references; no source content is stored."""

import sqlalchemy as sa
from alembic import op

revision = "0003_evidence"
down_revision = "0002_model_scores"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("source_version", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "idempotency_key"),
    )
    op.create_index("ix_evidence_references_case_id", "evidence_references", ["case_id"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_evidence_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Evidence references are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER immutable_evidence_references
            BEFORE UPDATE OR DELETE OR TRUNCATE ON evidence_references
            FOR EACH STATEMENT EXECUTE FUNCTION reject_evidence_mutation()
        """)


def downgrade():
    op.drop_table("evidence_references")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_evidence_mutation()")

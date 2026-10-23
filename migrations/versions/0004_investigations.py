"""Immutable investigation submissions with server-built evidence snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0004_investigations"
down_revision = "0003_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investigation_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("summary", sa.String(4000), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "idempotency_key"),
        sa.CheckConstraint("status = 'awaiting_review'", name="ck_investigation_pending"),
        sa.CheckConstraint(
            "disposition IN ('escalate', 'no_further_action', 'insufficient_evidence')",
            name="ck_investigation_disposition",
        ),
    )
    op.create_index("ix_investigation_records_case_id", "investigation_records", ["case_id"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_investigation_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Investigation records are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER immutable_investigation_records
            BEFORE UPDATE OR DELETE OR TRUNCATE ON investigation_records
            FOR EACH STATEMENT EXECUTE FUNCTION reject_investigation_mutation()
        """)


def downgrade():
    op.drop_table("investigation_records")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_investigation_mutation()")

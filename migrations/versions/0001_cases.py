"""Cases and append-only audit events. No existing portfolio tables are modified."""

import sqlalchemy as sa
from alembic import op

revision = "0001_cases"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(30), nullable=False),
        sa.Column("source_record_id", sa.String(500), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("event", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_case_id", "audit_events", ["case_id"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_audit_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Audit events are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER immutable_audit_events
            BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_events
            FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()
        """)


def downgrade():
    op.drop_table("audit_events")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_audit_mutation()")
    op.drop_table("cases")

"""Append-only workflow completion records and human review decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0005_reviews_runs"
down_revision = "0004_investigations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investigation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigation_records.id"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("workflow_version", sa.String(80), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "idempotency_key"),
    )
    op.create_index("ix_investigation_runs_case_id", "investigation_runs", ["case_id"])
    op.create_table(
        "investigation_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "investigation_id", sa.Uuid(), sa.ForeignKey("investigation_records.id"), nullable=False
        ),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("rationale", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investigation_id"),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'request_changes')", name="ck_review_decision"
        ),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_workflow_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Workflow records are append-only'; END;
            $$
        """)
        for table in ("investigation_runs", "investigation_reviews"):
            op.execute(f"""
                CREATE TRIGGER immutable_{table}
                BEFORE UPDATE OR DELETE OR TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION reject_workflow_mutation()
            """)


def downgrade():
    op.drop_table("investigation_reviews")
    op.drop_table("investigation_runs")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_workflow_mutation()")

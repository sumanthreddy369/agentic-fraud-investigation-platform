"""Immutable model score provenance linked to authorized cases."""

import sqlalchemy as sa
from alembic import op

revision = "0002_model_scores"
down_revision = "0001_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_score_references",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(30), nullable=False),
        sa.Column("model_version", sa.String(500), nullable=False),
        sa.Column("input_schema_version", sa.String(500), nullable=False),
        sa.Column("positive_class", sa.String(500), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("backend", sa.String(128), nullable=True),
        sa.Column("artifact_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="ck_score_probability"),
        sa.UniqueConstraint("case_id", "idempotency_key"),
    )
    op.create_index("ix_model_score_references_case_id", "model_score_references", ["case_id"])
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION reject_score_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'Model score references are append-only';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER immutable_model_score_references
            BEFORE UPDATE OR DELETE OR TRUNCATE ON model_score_references
            FOR EACH STATEMENT EXECUTE FUNCTION reject_score_mutation()
        """)


def downgrade():
    op.drop_table("model_score_references")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION reject_score_mutation()")

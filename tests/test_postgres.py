import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from risk_platform.contracts import (
    CaseCreate,
    Domain,
    EvidenceCreate,
    InvestigationCreate,
    InvestigationRunCreate,
    ModelAvailability,
    ReviewCreate,
    ScoreRequest,
    ScoreResult,
)
from risk_platform.database import make_engine, make_sessions
from risk_platform.service import CaseService, IdempotencyConflict

pytestmark = pytest.mark.postgres


async def test_workflow_review_races_and_append_only(postgres_url):
    pytest.importorskip("langgraph")
    engine = make_engine(postgres_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(run_migration, "up")
        sessions = make_sessions(engine)
        async with sessions() as session:
            case, _ = await CaseService(session, "owner").create(
                CaseCreate(domain="ieee_cis", source_record_id="fixture", title="Review"), "case"
            )

        async def run():
            async with sessions() as session:
                return await CaseService(session, "owner").run_investigation(
                    case.id, InvestigationRunCreate(query="review", score_ids=[]), "run"
                )

        results = await asyncio.gather(*(run() for _ in range(4)))
        assert sum(created for _, created in results) == 1
        assert len({record.id for record, _ in results}) == 1
        investigation_id = results[0][0].investigation_id

        async def review(decision="approve"):
            async with sessions() as session:
                return await CaseService(session, "owner").review_investigation(
                    investigation_id,
                    ReviewCreate(decision=decision, rationale="Reviewed"),
                    "review",
                )

        reviews = await asyncio.gather(*(review() for _ in range(4)))
        assert sum(created for _, created in reviews) == 1
        with pytest.raises(IdempotencyConflict):
            await review("reject")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM investigation_records")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 3
        for table in ("investigation_runs", "investigation_reviews"):
            for statement in (
                f"UPDATE {table} SET request_hash = 'tampered'",
                f"DELETE FROM {table}",
                f"TRUNCATE {table}",
            ):
                with pytest.raises(DBAPIError, match="append-only"):
                    async with engine.begin() as connection:
                        await connection.execute(text(statement))

        async with engine.begin() as connection:
            await connection.execute(
                text("""
                CREATE FUNCTION fail_workflow_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic audit failure'; END; $$
            """)
            )
            await connection.execute(
                text("""
                CREATE TRIGGER fail_workflow_audit BEFORE INSERT ON audit_events
                FOR EACH ROW EXECUTE FUNCTION fail_workflow_audit()
            """)
            )
        with pytest.raises(DBAPIError):
            async with sessions() as session:
                await CaseService(session, "owner").run_investigation(
                    case.id, InvestigationRunCreate(query="review", score_ids=[]), "failed"
                )
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM investigation_records")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM investigation_runs")) == 1
    finally:
        await engine.dispose()


def run_migration(connection, direction):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    if direction == "up":
        command.upgrade(config, "head")
    else:
        command.downgrade(config, "base")


async def test_migration_round_trip_and_concurrent_idempotency(postgres_url):
    engine = make_engine(postgres_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(run_migration, "up")
            await connection.run_sync(run_migration, "down")
            await connection.run_sync(run_migration, "up")
        sessions = make_sessions(engine)
        payload = CaseCreate(domain="elliptic", source_record_id="node-1", title="Graph alert")

        async def create():
            async with sessions() as session:
                return await CaseService(session, "investigator").create(payload, "same-key")

        results = await asyncio.gather(*(create() for _ in range(6)))
        assert len({case.id for case, _ in results}) == 1
        assert sum(created for _, created in results) == 1
        case = results[0][0]
        async with sessions() as session:
            cases = CaseService(session, "investigator")
            score_request = ScoreRequest(input_schema_version="v1", features={"amount": 1})
            await cases.record_score(
                case,
                "score-key",
                cases.score_request_hash(Domain.GRAPH, score_request),
                ScoreResult(
                    domain=Domain.GRAPH,
                    model_version="fixture-v1",
                    input_schema_version="v1",
                    positive_class="fraud",
                    probability=0.7,
                ),
                ModelAvailability(
                    domain=Domain.GRAPH,
                    available=True,
                    reason="fixture",
                    backend="fixture-runtime",
                    model_version="fixture-v1",
                    artifact_sha256="b" * 64,
                ),
            )
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 2
            assert await connection.scalar(text("SELECT count(*) FROM model_score_references")) == 1
            assert await connection.scalar(text("SHOW statement_timeout")) == "5s"
            assert await connection.scalar(text("SHOW lock_timeout")) == "1s"
            assert (
                await connection.scalar(text("SHOW idle_in_transaction_session_timeout")) == "10s"
            )
        for statement in (
            "UPDATE audit_events SET actor_id = 'tampered'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(text(statement))
        for statement in (
            "UPDATE model_score_references SET probability = 0.1",
            "DELETE FROM model_score_references",
            "TRUNCATE model_score_references",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(text(statement))

        # Alembic autogeneration should see no drift from the committed ORM metadata.
        def check(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.check(config)

        async with engine.begin() as connection:
            await connection.run_sync(check)
    finally:
        await engine.dispose()


async def test_investigation_upgrade_races_immutability_and_atomicity(postgres_url):
    engine = make_engine(postgres_url)
    try:

        def previous_revision(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0003_evidence")

        async with engine.begin() as connection:
            await connection.run_sync(previous_revision)
        sessions = make_sessions(engine)
        async with sessions() as session:
            service = CaseService(session, "owner")
            case, _ = await service.create(
                CaseCreate(domain="elliptic", source_record_id="synthetic", title="Upgrade"), "c"
            )
            evidence, _ = await service.add_evidence(
                case.id,
                EvidenceCreate(source_id="synthetic", source_version="v1", content_sha256="a" * 64),
                "e",
            )
        async with engine.begin() as connection:
            await connection.run_sync(run_migration, "up")
        payload = InvestigationCreate(
            disposition="escalate", summary="Synthetic recommendation", evidence_ids=[evidence.id]
        )

        async def submit(request, key):
            async with sessions() as session:
                return await CaseService(session, "owner").submit_investigation(
                    case.id, request, key
                )

        results = await asyncio.gather(*(submit(payload, "same") for _ in range(6)))
        record_id = results[0][0].id
        assert {record.id for record, _ in results} == {record_id}
        assert sum(created for _, created in results) == 1
        competing = await asyncio.gather(
            submit(payload, "conflict"),
            submit(payload.model_copy(update={"summary": "Other recommendation"}), "conflict"),
            return_exceptions=True,
        )
        assert sum(isinstance(result, IdempotencyConflict) for result in competing) == 1
        await engine.dispose()
        engine = make_engine(postgres_url)
        sessions = make_sessions(engine)
        async with sessions() as session:
            record = await CaseService(session, "owner").get_investigation(record_id)
            assert record.evidence[0]["source_version"] == "v1"
            assert record.evidence[0]["content_sha256"] == "a" * 64
            assert record.status == "awaiting_review"
        for statement in (
            "UPDATE investigation_records SET summary = 'tampered'",
            "DELETE FROM investigation_records",
            "TRUNCATE investigation_records CASCADE",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(text(statement))
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                CREATE FUNCTION fail_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic audit failure'; END; $$
            """)
            )
            await connection.execute(
                text("""
                CREATE TRIGGER fail_test_audit BEFORE INSERT ON audit_events
                FOR EACH ROW EXECUTE FUNCTION fail_test_audit()
            """)
            )
        with pytest.raises(DBAPIError):
            await submit(payload, "failed-audit")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM investigation_records")) == 2
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 4
    finally:
        await engine.dispose()


async def test_evidence_upgrade_race_restart_and_immutability(postgres_url):
    engine = make_engine(postgres_url)
    try:

        def previous_revision(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0002_model_scores")

        async with engine.begin() as connection:
            await connection.run_sync(previous_revision)
        sessions = make_sessions(engine)
        async with sessions() as session:
            case, _ = await CaseService(session, "owner").create(
                CaseCreate(domain="elliptic", source_record_id="synthetic", title="Upgrade"), "c"
            )
        async with engine.begin() as connection:
            await connection.run_sync(run_migration, "up")
        payload = EvidenceCreate(
            source_id="synthetic", source_version="v1", content_sha256="a" * 64
        )

        async def insert():
            async with sessions() as session:
                return await CaseService(session, "owner").add_evidence(case.id, payload, "same")

        results = await asyncio.gather(*(insert() for _ in range(6)))
        assert sum(created for _, created in results) == 1
        evidence_id = results[0][0].id
        assert {record.id for record, _ in results} == {evidence_id}
        await engine.dispose()
        engine = make_engine(postgres_url)
        async with make_sessions(engine)() as session:
            records = await CaseService(session, "owner").list_evidence(case.id)
            assert [record.id for record in records] == [evidence_id]
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 2
        for statement in (
            "UPDATE evidence_references SET source_version = 'tampered'",
            "DELETE FROM evidence_references",
            "TRUNCATE evidence_references",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with engine.begin() as connection:
                    await connection.execute(text(statement))
        # A failed audit insert must roll back the evidence row in the same transaction.
        async with engine.begin() as connection:
            await connection.execute(
                text("""
                CREATE FUNCTION fail_test_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic audit failure'; END; $$
            """)
            )
            await connection.execute(
                text("""
                CREATE TRIGGER fail_test_audit BEFORE INSERT ON audit_events
                FOR EACH ROW EXECUTE FUNCTION fail_test_audit()
            """)
            )
        with pytest.raises(DBAPIError):
            async with make_sessions(engine)() as session:
                await CaseService(session, "owner").add_evidence(case.id, payload, "failed-audit")
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM evidence_references")) == 1
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 2
    finally:
        await engine.dispose()

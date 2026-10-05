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
    ModelAvailability,
    ScoreRequest,
    ScoreResult,
)
from risk_platform.database import make_engine, make_sessions
from risk_platform.service import CaseService

pytestmark = pytest.mark.postgres


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

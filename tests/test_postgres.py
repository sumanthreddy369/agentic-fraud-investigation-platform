import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from risk_platform.contracts import CaseCreate
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
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT count(*) FROM audit_events")) == 1
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

        # Alembic autogeneration should see no drift from the committed ORM metadata.
        def check(connection):
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.check(config)

        async with engine.begin() as connection:
            await connection.run_sync(check)
    finally:
        await engine.dispose()

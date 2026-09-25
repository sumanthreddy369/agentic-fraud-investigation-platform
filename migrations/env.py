import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from risk_platform.config import Settings
from risk_platform.database import Base

config = context.config
target_metadata = Base.metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(
        Settings().database_url.get_secret_value(), poolclass=pool.NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(online())

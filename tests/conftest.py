import asyncio
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from risk_platform.config import Settings
from risk_platform.database import make_engine
from risk_platform.main import create_app

TOKEN = "test-only-operator-token-with-32-characters"


def migrate(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


@pytest.fixture
def database_url(tmp_path):
    return f"sqlite+aiosqlite:///{tmp_path / 'cases.db'}"


@pytest.fixture
async def client(database_url):
    engine = make_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(migrate)
    await engine.dispose()
    settings = Settings(
        _env_file=None, database_url=database_url, api_token=TOKEN, environment="test"
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as api:
            yield api, app


@pytest.fixture
async def postgres_url():
    raw = os.environ.get("RISK_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("RISK_TEST_DATABASE_URL not set; PostgreSQL tests not executed")
    url = make_url(raw)
    if url.drivername != "postgresql+psycopg":
        pytest.fail("RISK_TEST_DATABASE_URL must use postgresql+psycopg")
    # Isolate every test in its own schema; never drop caller-owned data.
    schema = "risk_test_" + uuid4().hex
    admin = make_engine(raw)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = url.update_query_dict({"options": f"-csearch_path={schema}"})
    try:
        yield isolated.render_as_string(hide_password=False)
    finally:
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def pytest_asyncio_loop_factories(config, item):
    return {"selector": asyncio.SelectorEventLoop}

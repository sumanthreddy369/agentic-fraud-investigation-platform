# Risk Investigation Platform

An additive investigation layer for the existing AWS Risk Portfolio. The original IEEE-CIS, Home Credit, and Elliptic components are not copied, retrained, or modified by this service.

## Implemented in increment 1

- FastAPI and Pydantic contracts, domain-separated case creation and listing.
- SQLAlchemy async sessions, psycopg 3, bounded PostgreSQL connection pooling.
- Alembic migrations for cases and audit events; PostgreSQL triggers reject audit updates, deletes, and truncation.
- Transactional case/audit creation and owner-scoped idempotency keys. Replays return the original case; conflicting reuse returns HTTP 409.
- Local operator bearer authentication, owner-filtered reads, fail-closed access when no token is configured.
- An adapter protocol and explicit unavailable status for all three existing models. **No scoring implementation or fabricated predictions.**
- Liveness, migration-aware readiness, request correlation IDs, reproducible dependency lock, and tests.

This is a local foundation, not a completed agentic platform. LangGraph, MCP, Qdrant, Azure OpenAI, OIDC/MSAL, document ETL, and human review screens remain future increments in [the plan](AGENTIC_FRAUD_PLATFORM_PLAN.md). Swagger `/docs` is the initial API exploration interface. There is no review/approval endpoint yet.

## Guardrails and showcase

The guardrail increment adds role/domain restrictions, bounded requests, throttling, safe errors, security headers, model timeouts/circuit breaking, database deadlines and operational disable switches. Authenticated `GET /v1/guardrails` exposes a safe control inventory.

[Guardrail matrix and demo guide](docs/GUARDRAILS.md) lists what is enforced, what is a tested agent-policy library, and what requires enterprise infrastructure. Run `uv run python scripts/demo_guardrails.py` for a synthetic demonstration without a running database or cloud credentials. See [captured demo results](docs/GUARDRAIL_DEMO_REPORT.json).

The agent policy library does not yet connect to LangGraph/MCP/Azure. Human-review packets cannot execute actions; an actual durable analyst approval workflow remains pending.

## Local setup (PowerShell)

Requires Python 3.11-3.13, uv, and Docker with Linux containers, or a separately configured PostgreSQL 16/17 instance. Use a dedicated **new database**, never an existing portfolio database.

```powershell
uv sync --frozen --python 3.11
Copy-Item .env.example .env
```

Set `RISK_API_TOKEN` in `.env` to a random value of at least 32 characters. For example, generate one with `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep it private. The default database credentials in `.env.example` and Compose are strictly for loopback-only local development.

```powershell
docker compose up -d --wait
uv run alembic upgrade head
uv run risk-platform
```

The launcher uses a psycopg-compatible selector event loop on Windows and binds only to loopback.

Open http://127.0.0.1:8000/docs, select **Authorize**, and enter the token. Create a case through `POST /v1/cases` with an `Idempotency-Key` header and this synthetic example:

```json
{"domain":"ieee_cis","source_record_id":"example-transaction-123","title":"Review transaction alert"}
```

The case stores a source reference, not raw transaction data. Valid domains are `ieee_cis`, `home_credit`, and `elliptic`. They have distinct entity IDs; no cross-dataset joins are inferred.

- `GET /v1/cases`: paginated case queue (`limit`, `offset`).
- `GET /v1/cases/{case_id}`: fetch an owned case.
- `GET /v1/cases/{case_id}/audit`: chronological audit events.
- `GET /v1/models`: list unresolved model integrations.
- `POST /v1/models/{domain}/score`: currently returns 503 until a verified adapter is implemented.
- `/health/live`: process liveness. `/health/ready`: current case schema; does **not** imply model/agent readiness.

A single local token maps to the configured server-side `RISK_OPERATOR_ID`. This is not multi-user OAuth or enterprise authorization. `RISK_ENVIRONMENT` accepts only `local`/`test`; keep the server bound to loopback until OIDC, role authorization, and deployment controls are added.

## Tests

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

By default, API tests use temporary SQLite databases for fast feedback; PostgreSQL-specific tests are explicitly skipped. To run real PostgreSQL tests against a dedicated test database:

```powershell
$env:RISK_TEST_DATABASE_URL = 'postgresql+psycopg://risk_local:risk_local@localhost:55432/risk_platform'
uv run pytest -q
```

Each PostgreSQL test creates and drops its own random schema, including all objects inside that schema. Use credentials with schema creation permission in a test database only. CI provisions PostgreSQL 17 and runs these tests.

On Windows with PostgreSQL binaries installed, an alternative avoids Docker and system database credentials:

```powershell
uv run python scripts/test_with_local_postgres.py --bin-dir 'C:\Program Files\PostgreSQL\17\bin'
```

This starts a temporary password-protected cluster on loopback and a dynamically selected port, runs the tests, stops it, and removes only its own temporary directory. It does not connect to or modify the installed PostgreSQL service.

## Preservation and next increment

The inspected GitHub repositories contain example code and documented results, but no committed saved models or datasets. See [baseline inventory](docs/BASELINE_INVENTORY.md). Before any real scoring adapter can be enabled, recover the authoritative model, preprocessing, class mapping, feature order, dependency versions, and golden inference fixtures. No existing model environment should be upgraded to match this service.

Pending inputs: authoritative portfolio checkout/artifact locations, AWS inference contracts, and the GitHub destination for this branch. GitHub publication is still pending; no remote has been selected.

The next increment should connect one verified scoring adapter and persist its provenance. Then add evidence retrieval and durable LangGraph review workflows. Missing models must remain visibly unavailable throughout.

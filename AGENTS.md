# AGENTS.md

## Project overview

This repository is a guarded FastAPI service for the existing IEEE-CIS fraud, Home Credit credit-risk, and Elliptic graph-fraud model boundaries. It persists cases, audit events, and model-score provenance in PostgreSQL. It loads explicitly configured ONNX models and contains a policy library for future agent investigations.

The API, database, HTTP guardrails, and ONNX adapter are implemented. LangGraph, MCP, external model providers, retrieval, graph infrastructure, AWS deployment, and human-review endpoints are targets. Do not describe them as working runtime features.

## Structure map

```text
src/risk_platform/        FastAPI runtime, contracts, services, persistence, scoring, and policies
migrations/               Alembic revisions and PostgreSQL immutability triggers
tests/                    SQLite tests and optional PostgreSQL integration tests
scripts/                  Guardrail demo and disposable PostgreSQL test runner
docs/                     Dataset, guardrail, ONNX, AWS target, baseline, and progress docs
.github/workflows/ci.yml  Locked Python 3.11 CI checks
compose.yaml              Loopback-only PostgreSQL 17 service
pyproject.toml            Package, dependency, script, and tool configuration
uv.lock                   Locked dependencies
```

Key modules:

- `main.py` owns app creation, dependencies, routes, and exception handlers.
- `http_guardrails.py` owns request admission and response hardening.
- `authorization.py` owns role, action, and domain checks.
- `contracts.py` owns external data contracts.
- `service.py` owns case and score transactions and idempotency.
- `database.py` owns ORM records, UTC handling, and engine construction.
- `scoring.py` owns registration, timeouts, locks, and circuit state.
- `onnx_adapter.py` owns manifest and runtime validation.
- `agent_policy.py` owns the bounded investigation policy.

## Build, test, and lint commands

```powershell
uv sync --frozen --python 3.11 --extra onnx-cpu
docker compose up -d --wait
uv run alembic upgrade head
uv run risk-platform
```

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run python scripts/demo_guardrails.py
```

Full PostgreSQL tests on Windows:

```powershell
uv run python scripts/test_with_local_postgres.py --bin-dir "C:\Program Files\PostgreSQL\17\bin"
```

Optional OpenVINO tests on Windows:

```powershell
uv sync --frozen --python 3.11 --extra onnx-openvino
uv run pytest -q tests/test_onnx_adapter.py
```

CI security checks:

```powershell
uv run bandit -r src -q
uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file /tmp/risk-runtime-requirements.txt
uv run pip-audit -r /tmp/risk-runtime-requirements.txt --no-deps --disable-pip
```

## Code conventions

- Support Python 3.11 through 3.13. Use explicit type hints at service boundaries.
- Use async SQLAlchemy and psycopg for runtime database work.
- Keep Pydantic request models strict. Reject unknown fields and bound user input.
- Keep routes thin. Put persistence in `CaseService`, access in `AuthorizationPolicy`, and execution in `ScoringGateway` or an adapter.
- Preserve fail-closed defaults for auth, models, migrations, and manifests.
- Return generic client errors. Never expose paths, SQL, stacks, secrets, or raw exceptions.
- Use aware UTC timestamps. `UTCDateTime` rejects naive values.
- Preserve owner and domain filters on case, audit, and score queries.
- Bind idempotency keys to canonical hashes. Resolve uniqueness races by re-reading the winner.
- Keep audit events and score references append-only in PostgreSQL.
- Run blocking inference through `asyncio.to_thread`.
- Keep inference bounded by one call per domain, a timeout, and a circuit breaker. Do not add hidden retries.
- Follow Ruff in `pyproject.toml`: line length 100 and `E`, `F`, `I`, `UP`, and `B` rules.
- Name tests `test_*.py`. Mark real PostgreSQL tests with `postgres`.

## Do

- Read implementation and migrations before changing behavior or documentation.
- Preserve the IEEE-CIS, Home Credit, and Elliptic boundaries.
- Add migrations for schema changes and keep ORM definitions synchronized.
- Add focused tests for behavior changes. Use PostgreSQL tests for constraints and triggers.
- Run Ruff and the relevant pytest suites before committing.
- Keep request, evidence, feature, and output sizes bounded.
- Store model identity, schema, artifact hash, backend, class meaning, actor, and request hash with score provenance.
- Keep human review authoritative for future investigations.
- Mark unimplemented architecture as `Target (not built yet)`.
- Keep datasets, models, outputs, secrets, and local database state out of Git.

## Don't

- Do not replace or retrain existing portfolio models unless explicitly requested.
- Do not mark a model available when its manifest, hash, provider, or tensor contract fails.
- Do not accept actors, roles, or domains from request headers.
- Do not trust `X-Forwarded-For` without a trusted-proxy design.
- Do not persist raw model features in score rows.
- Do not log bodies, tokens, sensitive evidence, or raw exceptions.
- Do not mutate or delete audit events or score references.
- Do not bypass idempotency, authorization, kill switches, timeouts, or circuits.
- Do not claim LangGraph, MCP, Bedrock, Azure OpenAI, Qdrant, Neptune, Kafka, Kinesis, Feast, MLflow, or AWS deployment is implemented until executable code and tests exist.
- Do not send recommendations directly to enforcement actions. Future packets require human approval.

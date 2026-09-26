# Implementation progress

## Increment 1 — 2026-09-25

Completed a local, additive API foundation. No files in the three existing risk repositories were changed.

- FastAPI/Pydantic case contracts and explicit per-domain model availability.
- PostgreSQL persistence with async SQLAlchemy/psycopg, Alembic migration, and bounded pooling.
- Idempotent case creation with a transactional audit event; owner-scoped case and audit reads.
- Local operator token access, a loopback-only Windows-compatible launcher, and migration-aware readiness.
- Dependency lock, Docker Compose database definition, GitHub Actions workflow, documentation, and isolated database tests.

Validation: 16 tests passed on Python 3.11.9 with a disposable PostgreSQL 17.4 cluster. This includes case persistence across application restart, access isolation, invalid inputs, absent-model behavior, migration round-trip, schema drift detection, six concurrent duplicate requests, and audit update/delete/truncate rejection. SQLite API tests and real PostgreSQL checks are distinguished in the test suite. The temporary cluster was stopped and cleaned up. Docker was unavailable, so the locally installed PostgreSQL binaries supplied the isolated test runtime.

GitHub Actions has been authored but has not run remotely. No application or database is deployed. No real model was loaded, scored, or retrained. Reported historical model metrics remain unverified.

## Outstanding before verified model scoring

- Authoritative portfolio checkout and saved model/preprocessing/dataset locations.
- Feature, class-label, schema, and inference contracts, plus golden prediction fixtures.

Phase 1 is partial: real model adapters, score provenance persistence, enterprise identity, and investigator UI are not yet implemented. LangGraph, MCP, Qdrant, Azure OpenAI, retrieval/ETL, and human review are subsequent increments. Do not label this foundation as a completed agentic platform.

## Increment 2 — guardrails

Implemented live API controls for server-configured roles and domains, bounded request bodies/headers, slow-body deadlines, per-peer throttling, concurrency limits, trusted hosts, sanitized errors, safe structured event logging, security headers, bounded audit pagination, database deadlines, model output validation, scoring timeouts/circuit breaking, and write/scoring disable switches.

Added a separately tested agent-policy library: read-only tool allowlist, trusted case context, scoped evidence, execution/evidence budgets, default-deny external-AI payload preparation, evidence classification/approval checks, citation validation, abstention, and mandatory human-review packets. These policies are not yet connected to LangGraph, MCP or Azure; there is no autonomous business-action executor or durable review workflow.

Verification completed: **62 tests passed** on Python 3.11.9 using a disposable PostgreSQL 17.4 cluster. **14 synthetic showcase checks passed**. Ruff lint/format and Bandit static analysis passed. The saved pip-audit report found no known vulnerabilities in the 23 locked runtime dependencies checked on 2026-09-25; this is a point-in-time advisory check, not proof of security. The temporary database was stopped and removed.

See `GUARDRAILS.md` for the implemented/policy-only/deployment-required control matrix, `GUARDRAIL_DEMO_REPORT.json` for showcase evidence, and `DEPENDENCY_AUDIT.json` for the dependency report. CI includes the showcase and security-scanning gates. Remote run results are available in the repository Actions tab.

## Source publication

Public destination: [agentic-fraud-investigation-platform](https://github.com/sumanthreddy369/agentic-fraud-investigation-platform). The published source includes the implementation plan, API foundation, guardrails, tests, documentation and saved verification reports. It excludes local environments, credentials, test database files and the original model/dataset artifacts. Source publication does not deploy the application or provision cloud infrastructure.

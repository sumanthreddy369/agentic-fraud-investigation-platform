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
- Chosen GitHub repository destination (this workspace has no remote).

Phase 1 is partial: real model adapters, score provenance persistence, enterprise identity, and investigator UI are not yet implemented. LangGraph, MCP, Qdrant, Azure OpenAI, retrieval/ETL, and human review are subsequent increments. Do not label this foundation as a completed agentic platform.

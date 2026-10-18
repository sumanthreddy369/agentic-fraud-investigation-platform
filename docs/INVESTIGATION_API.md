# Investigation execution and human review

The API connects existing case scores to the bounded LangGraph workflow and records a
human decision against the resulting investigation. This is a local operator workflow;
it does not establish multi-user reviewer assignment or banking integration.

## Setup

```powershell
uv sync --frozen --python 3.11 --extra onnx-cpu --extra agents
uv run alembic upgrade head
$env:RISK_INVESTIGATIONS_ENABLED = "true"
uv run risk-platform
```

The default container does not install the agents extra. Enable execution only with
that extra installed; an absent dependency returns a generic 503. Schema readiness
requires `0005_reviews_runs`.

## API sequence

All routes require the configured bearer token. Roles and ownership come from server
configuration, never request headers. POST routes require an `Idempotency-Key`.

1. Create a case and score it through the existing case scoring endpoint.
2. As investigator, POST `/v1/cases/{case_id}/investigation-runs` with
   `{"query":"Review selected scores","score_ids":["<existing-score-uuid>"]}`.
3. GET `/v1/investigations/{investigation_id}` using the returned investigation ID.
4. With the server configured for the reviewer role under the same case owner, POST
   `/v1/investigations/{investigation_id}/review` with
   `{"decision":"request_changes","rationale":"Obtain supporting evidence."}`.
5. GET the same review URL to retrieve the stored decision.

Each run accepts at most 20 unique score IDs. The service checks case ownership, domain,
and every score reference, then passes immutable score metadata to its read-only tool.
It does not fetch URLs, read raw features, run inference again, or contact an external
provider. The bounded query is hashed for replay, not persisted in plain text. Score IDs
explicitly select inputs; the query does not perform a search.

The workflow always returns `insufficient_evidence`: scores alone do not prove fraud.
Its completion record preserves score identity, version, backend, artifact hash, class
meaning, and probability. The packet contains no invented citations.

## Persistence and review semantics

The completion record, investigation, and audit event commit in one transaction.
Same-key/same-input replay returns the original completion after application restart.
Changed input returns 409. Concurrent duplicates may repeat the bounded read-only graph,
but database uniqueness permits only one committed completion. There is no claim of
exactly-once graph execution or crash recovery inside a node.

A reviewer records `approve`, `reject`, or `request_changes`. Each investigation has
one immutable decision. An identical key and payload replays; a different key or payload
conflicts. Corrections require a new investigation. PostgreSQL triggers reject update,
delete, and truncate on run and review records. The original submission remains an
immutable `awaiting_review` snapshot; read its separate review resource to determine
whether a decision exists. `requires_human_review` expresses policy, not live queue state.

Approval never changes case status or triggers enforcement. Investigators and auditors
cannot submit reviews. This single-operator role configuration does not prove independent
two-person approval: OIDC and reviewer assignment remain **Target (not built yet)**.
The global write switch disables runs and reviews; the separate investigation switch
disables graph execution. Bedrock drafting and MCP transport are also targets.

Tests cover API replay and restart, score isolation, ownership and domains, permissions,
write switches, concurrent PostgreSQL commits, audit rollback, migration round trips,
ORM parity, and append-only triggers.

## Validation — October 18, 2026

The complete suite using a disposable local PostgreSQL instance finished with **192
passed and 1 skipped**. The temporary database was stopped afterward. Ruff lint and
format checks, Bandit, and all 14 guardrail demonstration checks passed. These are local
engineering results; they are not AWS deployment or live fraud investigation results.

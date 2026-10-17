# Investigation workflow

`src/risk_platform/investigation_workflow.py` implements a bounded local LangGraph
workflow on top of the existing investigation policy. It reads case-scoped evidence
and produces a review packet. It does not approve transactions, close cases, or
invoke enforcement tools.

Install the `agents` extra to run it. The caller supplies an authorized
`InvestigationScope`, approved read-only tool implementations and a checkpointer.
SQLite checkpoint tests cover closing and reopening the store. Scope and run ID
determine the checkpoint thread; a changed query for the same run is rejected.
Completed packets are returned without repeating the evidence call. An incomplete
run requires explicit operator handling instead of an automatic retry.

External drafting is disabled by default. An explicitly configured drafting callback
receives only evidence admitted by the existing external-evidence policy. A draft
must pass citation and output validation, and every packet requires human review.
Without a drafting callback, the workflow abstains. External tracing is rejected
when enabled through the standard LangChain/LangSmith tracing environment flags.

## Local test coverage

- Completed packet recovery from a reopened SQLite checkpoint store.
- Changed-input rejection for an existing run.
- Cross-case evidence rejection and no automatic retry of a failed run.
- Default-deny external drafting.
- Rejection of fabricated citation IDs.
- Case/owner checkpoint separation and mandatory human review.
- Rejection of unauthorized scope and enabled external tracing.

The drafting callbacks in tests are deterministic fixtures, not live language models.
Citation checks establish provenance, not semantic correctness or complete resistance
to prompt injection. The runner is intended for one trusted local process; its lock
is not a distributed lease. Crash recovery during a node does not provide exactly-once
external execution. Checkpoint files are private and are excluded from Git.

## Integration work

Authenticated API scheduling, PostgreSQL checkpoint operations, live Bedrock drafting,
MCP transport, retrieval indexing, reviewer decision endpoints and AWS deployment
remain Target (not built yet). Do not expose this local runner directly as a shared
service or accept checkpoint IDs and actor identities from model output.

The checkpoint integration follows [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

# Local investigation demonstration

Run from the repository root with the agents extra installed:

```powershell
uv sync --frozen --python 3.11 --extra agents
uv run python scripts/demo_investigation.py
```

The script constructs four synthetic evidence records, runs the LangGraph investigation,
closes the SQLite checkpoint connection, and creates a new workflow with a reopened connection.
Each invocation uses a new run directory under ignored `artifacts/investigation-demo/`.
It saves `review-packet.json`, `results.json`, and `checkpoints.db` locally.
It exits unsuccessfully if any check fails.

## Results — October 18, 2026

| Check | Observed result |
|---|---|
| Evidence scope | 1 of 4 records retrieved; other case, owner, and domain excluded |
| Retrieval execution | 1 call across initial execution and checkpoint reopen |
| Packet recovery | Recovered packet equals the original |
| Changed query with the same run ID | Rejected |
| Unauthorized actor | Rejected |
| Human review | Required on the saved packet |
| Default recommendation | `insufficient_evidence` |

All seven checks passed. This demonstration uses synthetic evidence and no external model,
network service, or AWS resource. Retrieval is local lexical matching. The default workflow
abstains: finding an excerpt is not sufficient to make a fraud decision. No enforcement action
is available. The packet contains no copied evidence excerpt.

Reopening the checkpoint demonstrates recovery of a completed run, not recovery from a crash
inside a node or distributed exactly-once execution. Model scoring and authenticated API
integration are separate from this local demonstration. Bedrock and MCP integration remain
**Target (not built yet)**.

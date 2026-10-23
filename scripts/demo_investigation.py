"""Exercise local investigation retrieval and checkpoint recovery with synthetic data."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from risk_platform.agent_policy import Evidence, InvestigationScope, PolicyDenied, ToolArguments
from risk_platform.contracts import Domain
from risk_platform.evidence_retrieval import LocalEvidenceRetriever
from risk_platform.investigation_workflow import InvestigationWorkflow


async def main() -> None:
    run_id = uuid4()
    output = Path("artifacts/investigation-demo") / str(run_id)
    output.mkdir(parents=True)
    scope = InvestigationScope(uuid4(), Domain.TRANSACTION, "demo-owner", "demo-owner")
    records = (
        Evidence("in-scope", scope.case_id, scope.domain, scope.owner_id, "Synthetic fraud review"),
        Evidence("other-case", uuid4(), scope.domain, scope.owner_id, "Synthetic fraud review"),
        Evidence("other-owner", scope.case_id, scope.domain, "other", "Synthetic fraud review"),
        Evidence(
            "other-domain", scope.case_id, Domain.GRAPH, scope.owner_id, "Synthetic fraud review"
        ),
    )
    retriever = LocalEvidenceRetriever(records)
    calls = 0
    retrieved_ids: list[str] = []

    async def retrieve(
        current: InvestigationScope, arguments: ToolArguments
    ) -> tuple[Evidence, ...]:
        nonlocal calls
        calls += 1
        result = await retriever(current, arguments)
        retrieved_ids.extend(item.id for item in result)
        return result

    database = str(output / "checkpoints.db")
    tools = {"get_case_evidence": retrieve}
    async with AsyncSqliteSaver.from_conn_string(database) as saver:
        packet = await InvestigationWorkflow(scope, tools, saver).run(run_id, "fraud review")
    calls_before_reopen = calls
    async with AsyncSqliteSaver.from_conn_string(database) as saver:
        workflow = InvestigationWorkflow(scope, tools, saver)
        recovered = await workflow.run(run_id, "fraud review")
        try:
            await workflow.run(run_id, "different query")
        except PolicyDenied as error:
            conflict_rejected = str(error) == "run_input_conflict"
        else:
            conflict_rejected = False

    unauthorized = InvestigationScope(scope.case_id, scope.domain, scope.owner_id, "other")
    try:
        await retriever(unauthorized, ToolArguments(query="fraud review"))
    except PolicyDenied as error:
        unauthorized_rejected = str(error) == "case_access_denied"
    else:
        unauthorized_rejected = False

    checks = {
        "scope_isolation": retrieved_ids == ["in-scope"],
        "checkpoint_packet_equal": recovered == packet,
        "no_repeat_retrieval": calls == calls_before_reopen == 1,
        "changed_query_rejected": conflict_rejected,
        "unauthorized_actor_rejected": unauthorized_rejected,
        "human_review_required": packet.requires_human_review is True,
        "default_abstention": packet.recommendation.disposition == "insufficient_evidence",
    }
    results = {
        "scope": "Local synthetic investigation; no model, external provider or AWS calls",
        "fixture_records": len(records),
        "retrieved_records": len(retrieved_ids),
        "retrieval_calls": calls,
        "checks": checks,
    }
    (output / "review-packet.json").write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"Artifacts: {output.resolve()}")
    if not all(checks.values()):
        raise RuntimeError("Investigation demo checks failed")


if __name__ == "__main__":
    asyncio.run(main())

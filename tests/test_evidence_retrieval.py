from dataclasses import replace
from uuid import uuid4

import pytest

from risk_platform.agent_policy import (
    Evidence,
    GuardedInvestigation,
    InvestigationScope,
    PolicyDenied,
    ToolArguments,
)
from risk_platform.contracts import Domain
from risk_platform.evidence_retrieval import LocalEvidenceRetriever


def fixture():
    scope = InvestigationScope(uuid4(), Domain.TRANSACTION, "alice", "alice")
    item = Evidence("e1", scope.case_id, scope.domain, scope.owner_id, "Repeated card attempts")
    return scope, item


async def test_filters_every_scope_dimension_before_ranking():
    scope, item = fixture()
    retriever = LocalEvidenceRetriever(
        [
            item,
            replace(item, owner_id="bob", excerpt="card attempts repeated suspicious"),
            replace(item, case_id=uuid4(), excerpt="card attempts repeated suspicious"),
            replace(item, domain=Domain.GRAPH, excerpt="card attempts repeated suspicious"),
        ],
        top_k=1,
    )
    assert await retriever(scope, ToolArguments(query="card attempts suspicious")) == (item,)
    with pytest.raises(PolicyDenied, match="case_access_denied"):
        await retriever(replace(scope, actor_id="bob"), ToolArguments(query="card"))


async def test_ranking_is_bounded_deterministic_and_lexical():
    scope, item = fixture()
    other = replace(item, id="e2", excerpt="card")
    retriever = LocalEvidenceRetriever([other, item], top_k=1)
    assert await retriever(scope, ToolArguments(query="CARD attempts")) == (item,)
    assert await retriever(scope, ToolArguments(query="card")) == (item,)
    assert await retriever(scope, ToolArguments(query="unrelated")) == ()
    assert await retriever(scope, ToolArguments(query="!!!")) == ()


async def test_retrieval_preserves_external_disclosure_gate():
    scope, item = fixture()
    guard = GuardedInvestigation(scope, {"get_case_evidence": LocalEvidenceRetriever([item])})
    assert await guard.call("get_case_evidence", {"query": "card"}) == (item,)
    with pytest.raises(PolicyDenied, match="external_ai_disabled"):
        guard.prepare_external_evidence([item.id])


def test_invalid_collection_and_configuration_rejected():
    _, item = fixture()
    for top_k in (0, 21, True, 1.5):
        with pytest.raises(ValueError):
            LocalEvidenceRetriever([item], top_k=top_k)
    for items in ([item, item], [replace(item, excerpt="x" * 4001)], [object()]):
        with pytest.raises(ValueError):
            LocalEvidenceRetriever(items)
    with pytest.raises(ValueError, match="1000"):
        LocalEvidenceRetriever(replace(item, id=str(i)) for i in range(1001))


async def test_retriever_runs_inside_checkpointed_workflow(tmp_path):
    pytest.importorskip("langgraph")
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from risk_platform.investigation_workflow import InvestigationWorkflow

    scope, item = fixture()
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "run.db")) as saver:
        workflow = InvestigationWorkflow(
            scope, {"get_case_evidence": LocalEvidenceRetriever([item])}, saver
        )
        packet = await workflow.run(uuid4(), "card attempts")
    assert packet.requires_human_review is True
    assert packet.recommendation.disposition == "insufficient_evidence"

"""Local LangGraph workflow that produces review packets, never enforcement actions."""

import asyncio
import hashlib
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from risk_platform.agent_policy import (
    AgentLimits,
    GuardedInvestigation,
    InvestigationScope,
    PolicyDenied,
    ReviewPacket,
    Tool,
    ToolArguments,
)

Draft = Callable[[list[dict[str, str]]], Awaitable[dict]]


class WorkflowState(TypedDict, total=False):
    query: str
    packet: dict


class InvestigationWorkflow:
    """Trusted local runner; authenticated API integration is a separate boundary.

    The fixed graph makes one evidence read and at most one drafting call. Completed
    packets are reusable after restart. It does not promise exactly-once execution
    if a process crashes during a node; external side-effecting tools are forbidden.
    """

    def __init__(
        self,
        scope: InvestigationScope,
        tools: Mapping[str, Tool],
        checkpointer,
        limits: AgentLimits | None = None,
        draft: Draft | None = None,
    ) -> None:
        if any(
            os.getenv(key, "").lower() in {"true", "1"}
            for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")
        ):
            raise PolicyDenied("external_tracing_not_allowed")
        self.scope = scope
        self.limits = limits or AgentLimits()
        # Validate the server-supplied scope before opening any checkpoint.
        GuardedInvestigation(scope, tools, self.limits)
        self.lock = asyncio.Lock()

        async def investigate(state: WorkflowState) -> WorkflowState:
            guard = GuardedInvestigation(scope, tools, self.limits)
            evidence = await guard.call("get_case_evidence", {"query": state["query"]})
            proposal = {
                "disposition": "insufficient_evidence",
                "summary": "Evidence requires investigator review.",
                "citations": [],
            }
            if evidence and draft is not None:
                payload = guard.prepare_external_evidence([item.id for item in evidence])
                try:
                    async with asyncio.timeout(self.limits.tool_timeout_seconds):
                        proposal = await draft(payload)
                except Exception:
                    raise PolicyDenied("draft_failed") from None
            packet = guard.review_packet(proposal)
            return {"packet": packet.model_dump(mode="json")}

        builder = StateGraph(WorkflowState)
        builder.add_node("investigate", investigate)
        builder.add_edge(START, "investigate")
        builder.add_edge("investigate", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    async def run(self, run_id: UUID, query: str) -> ReviewPacket:
        ToolArguments(query=query)
        identity = json.dumps(
            [
                self.scope.owner_id,
                self.scope.actor_id,
                str(self.scope.case_id),
                self.scope.domain.value,
                str(run_id),
            ],
            separators=(",", ":"),
        )
        config = {
            "configurable": {"thread_id": hashlib.sha256(identity.encode()).hexdigest()},
            "recursion_limit": 4,
        }
        async with self.lock:
            previous = await self.graph.aget_state(config)
            if previous.values:
                if previous.values.get("query") != query:
                    raise PolicyDenied("run_input_conflict")
                if "packet" in previous.values:
                    return ReviewPacket.model_validate(previous.values["packet"])
                # A failed/in-flight node requires explicit operator handling, not hidden retry.
                raise PolicyDenied("incomplete_run_requires_review")
            async with asyncio.timeout(self.limits.run_timeout_seconds):
                result = await self.graph.ainvoke({"query": query}, config)
            return ReviewPacket.model_validate(result["packet"])

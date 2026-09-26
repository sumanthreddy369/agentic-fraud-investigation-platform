"""Tested policy boundary for future LangGraph/MCP integration; no LLM or tools auto-connect."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from risk_platform.contracts import Contract, Domain


class PolicyDenied(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class InvestigationScope:
    # Construct from authenticated identity and an authorized case, never LLM arguments.
    case_id: UUID
    domain: Domain
    owner_id: str
    actor_id: str


@dataclass(frozen=True)
class Evidence:
    id: str
    case_id: UUID
    domain: Domain
    owner_id: str
    excerpt: str
    classification: Literal["public", "internal", "restricted"] = "restricted"
    external_approved: bool = False


class ToolArguments(Contract):
    query: Annotated[str, Field(min_length=1, max_length=2000)]


class Recommendation(Contract):
    disposition: Literal["escalate", "no_further_action", "insufficient_evidence"]
    summary: Annotated[str, Field(min_length=1, max_length=4000)]
    citations: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=128)]], Field(max_length=20)
    ]


class ReviewPacket(Contract):
    case_id: UUID
    domain: Domain
    recommendation: Recommendation
    requires_human_review: Literal[True] = True


class AgentLimits(Contract):
    model_config = {"extra": "forbid", "frozen": True}
    max_tool_calls: Annotated[int, Field(ge=1, le=20)] = 5
    max_evidence_items: Annotated[int, Field(ge=1, le=50)] = 20
    max_excerpt_chars: Annotated[int, Field(ge=1, le=10000)] = 4000
    tool_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5
    run_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30
    allow_external_ai: bool = False


Tool = Callable[[InvestigationScope, ToolArguments], Awaitable[tuple[Evidence, ...]]]
READ_ONLY_TOOLS = frozenset({"get_case_evidence", "search_policy", "get_graph_neighborhood"})
# Secondary heuristic only. Classification/approval and default-deny egress are the primary gates.
SENSITIVE_PATTERN = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{3}-\d{2}-\d{4}\b|"
    r"\b(?:\d[ -]?){13,19}\b|(?:api[_ -]?key|password|secret)\s*[:=]",
    re.I,
)


class GuardedInvestigation:
    def __init__(
        self,
        scope: InvestigationScope,
        tools: Mapping[str, Tool],
        limits: AgentLimits | None = None,
    ):
        if scope.actor_id != scope.owner_id:
            raise PolicyDenied("case_access_denied")
        self.scope = scope
        self.tools = dict(tools)
        self.limits = limits or AgentLimits()
        self.calls = 0
        self.started_at = time.monotonic()
        self.evidence: dict[str, Evidence] = {}
        self.lock = asyncio.Lock()

    async def call(self, tool_name: str, arguments: dict) -> tuple[Evidence, ...]:
        if tool_name not in READ_ONLY_TOOLS:
            # No shell, arbitrary SQL, URL fetching, payment, block, or approval tools.
            raise PolicyDenied("tool_not_allowed")
        if tool_name == "get_graph_neighborhood" and self.scope.domain != Domain.GRAPH:
            raise PolicyDenied("tool_domain_mismatch")
        if tool_name not in self.tools:
            raise PolicyDenied("tool_not_configured")
        parsed = ToolArguments.model_validate(arguments)
        if self.lock.locked():
            raise PolicyDenied("concurrent_tool_call_denied")
        async with self.lock:
            remaining = self.limits.run_timeout_seconds - (time.monotonic() - self.started_at)
            if remaining <= 0 or self.calls >= self.limits.max_tool_calls:
                raise PolicyDenied("run_budget_exhausted")
            self.calls += 1  # Failed calls also spend the budget; no hidden automatic retries.
            try:
                async with asyncio.timeout(min(remaining, self.limits.tool_timeout_seconds)):
                    result = await self.tools[tool_name](self.scope, parsed)
            except TimeoutError:
                raise PolicyDenied("tool_timeout") from None
            except Exception:
                raise PolicyDenied("tool_execution_failed") from None
            if not isinstance(result, tuple) or not all(
                isinstance(item, Evidence) for item in result
            ):
                raise PolicyDenied("invalid_tool_output")
            if len(result) > self.limits.max_evidence_items:
                raise PolicyDenied("evidence_budget_exhausted")
            self.ensure_live()
            pending = dict(self.evidence)
            for item in result:
                if (
                    item.case_id != self.scope.case_id
                    or item.domain != self.scope.domain
                    or item.owner_id != self.scope.owner_id
                ):
                    raise PolicyDenied("evidence_scope_mismatch")
                if (
                    not item.id
                    or len(item.id) > 128
                    or len(item.excerpt) > self.limits.max_excerpt_chars
                ):
                    raise PolicyDenied("invalid_evidence")
                if item.id in pending and pending[item.id] != item:
                    raise PolicyDenied("evidence_id_collision")
                pending[item.id] = item
            if len(pending) > self.limits.max_evidence_items:
                raise PolicyDenied("evidence_budget_exhausted")
            self.evidence = pending
            return result

    def ensure_live(self) -> None:
        if time.monotonic() - self.started_at >= self.limits.run_timeout_seconds:
            raise PolicyDenied("run_budget_exhausted")

    def prepare_external_evidence(self, evidence_ids: list[str]) -> list[dict[str, str]]:
        """Prepare an approved payload only. This method never performs a network call."""
        self.ensure_live()
        if not self.limits.allow_external_ai:
            raise PolicyDenied("external_ai_disabled")
        if len(evidence_ids) > self.limits.max_evidence_items:
            raise PolicyDenied("evidence_budget_exhausted")
        output = []
        for evidence_id in dict.fromkeys(evidence_ids):
            item = self.evidence.get(evidence_id)
            if item is None:
                raise PolicyDenied("unknown_evidence")
            if item.classification != "public" or item.external_approved is not True:
                raise PolicyDenied("external_evidence_not_approved")
            if SENSITIVE_PATTERN.search(item.excerpt):
                raise PolicyDenied("sensitive_content_detected")
            output.append({"evidence_id": item.id, "untrusted_excerpt": item.excerpt})
        return output

    def review_packet(self, proposal: dict) -> ReviewPacket:
        self.ensure_live()
        recommendation = Recommendation.model_validate(proposal)
        if len(set(recommendation.citations)) != len(recommendation.citations):
            raise PolicyDenied("duplicate_citations")
        if any(item not in self.evidence for item in recommendation.citations):
            raise PolicyDenied("unknown_citation")
        if not recommendation.citations and recommendation.disposition != "insufficient_evidence":
            raise PolicyDenied("evidence_required")
        # A valid citation proves provenance, not the truth of every generated claim.
        # This is a review packet; there is intentionally no execute/approve method.
        return ReviewPacket(
            case_id=self.scope.case_id, domain=self.scope.domain, recommendation=recommendation
        )

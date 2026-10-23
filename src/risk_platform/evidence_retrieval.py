"""Bounded lexical retrieval for explicitly supplied local case evidence."""

import re
from collections.abc import Iterable

from risk_platform.agent_policy import Evidence, InvestigationScope, PolicyDenied, ToolArguments

TOKEN = re.compile(r"\w+", re.UNICODE)


class LocalEvidenceRetriever:
    """Read-only tool compatible with GuardedInvestigation; no network or file discovery.

    Authorization filters precede ranking. This small in-memory implementation is
    for portfolio replay, not a shared production search service or vector index.
    """

    def __init__(self, evidence: Iterable[Evidence], *, top_k: int = 10) -> None:
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        items: list[Evidence] = []
        identities: set[tuple] = set()
        for item in evidence:
            if len(items) >= 1000:
                raise ValueError("Evidence collection exceeds 1000 items")
            if not isinstance(item, Evidence):
                raise ValueError("Invalid evidence item")
            if (
                not isinstance(item.id, str)
                or not 1 <= len(item.id) <= 128
                or not isinstance(item.excerpt, str)
                or not 1 <= len(item.excerpt) <= 4000
            ):
                raise ValueError("Invalid evidence fields")
            identity = (item.owner_id, item.case_id, item.domain, item.id)
            if identity in identities:
                raise ValueError("Duplicate scoped evidence identifier")
            identities.add(identity)
            items.append(item)
        self._items = tuple(items)
        self._top_k = top_k

    async def __call__(
        self, scope: InvestigationScope, arguments: ToolArguments
    ) -> tuple[Evidence, ...]:
        if scope.actor_id != scope.owner_id:
            raise PolicyDenied("case_access_denied")
        query = ToolArguments.model_validate(arguments).query
        terms = set(TOKEN.findall(query.casefold()))
        if not terms:
            return ()
        ranked: list[tuple[int, str, Evidence]] = []
        for item in self._items:
            if (item.owner_id, item.case_id, item.domain) != (
                scope.owner_id,
                scope.case_id,
                scope.domain,
            ):
                continue
            overlap = len(terms.intersection(TOKEN.findall(item.excerpt.casefold())))
            if overlap:
                ranked.append((overlap, item.id, item))
        ranked.sort(key=lambda entry: (-entry[0], entry[1]))
        return tuple(item for _, _, item in ranked[: self._top_k])

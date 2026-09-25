"""Explicit adapter boundary. No model loading, retraining, or synthetic fallback."""

from typing import Protocol

from risk_platform.contracts import Domain, ModelAvailability, ScoreRequest, ScoreResult


class ModelUnavailable(Exception):
    pass


class ModelAdapter(Protocol):
    def availability(self) -> ModelAvailability: ...

    async def score(self, request: ScoreRequest) -> ScoreResult: ...


class UnavailableAdapter:
    def __init__(self, domain: Domain):
        self.domain = domain

    def availability(self) -> ModelAvailability:
        return ModelAvailability(
            domain=self.domain,
            available=False,
            reason="Authoritative model, preprocessing, and inference contract not yet verified",
        )

    async def score(self, request: ScoreRequest) -> ScoreResult:
        raise ModelUnavailable(self.availability().reason)


class ModelRegistry:
    def __init__(self) -> None:
        self._adapters: dict[Domain, ModelAdapter] = {
            domain: UnavailableAdapter(domain) for domain in Domain
        }

    def get(self, domain: Domain) -> ModelAdapter:
        return self._adapters[domain]

    def availability(self) -> list[ModelAvailability]:
        return [self.get(domain).availability() for domain in Domain]

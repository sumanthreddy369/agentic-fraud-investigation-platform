"""Bounded model execution; invalid outputs and dependency failures never become scores."""

import asyncio
import time
from dataclasses import dataclass

from risk_platform.adapters import ModelRegistry, ModelUnavailable
from risk_platform.config import Settings
from risk_platform.contracts import Domain, ScoreRequest, ScoreResult


class ScoringFailure(Exception):
    def __init__(self, status: int, reason: str):
        self.status = status
        self.reason = reason


@dataclass
class Circuit:
    failures: int = 0
    opened_at: float | None = None


class ScoringGateway:
    def __init__(self, models: ModelRegistry, settings: Settings):
        self.models = models
        self.settings = settings
        self.circuits = {domain: Circuit() for domain in Domain}
        # One in-flight call per domain bounds model load and permits one recovery probe.
        self.locks = {domain: asyncio.Lock() for domain in Domain}

    async def score(self, domain: Domain, request: ScoreRequest) -> ScoreResult:
        if domain not in self.settings.allowed_domains:
            raise ScoringFailure(403, "Domain access denied")
        if not self.settings.scoring_enabled:
            raise ScoringFailure(503, "Model scoring is disabled")
        lock = self.locks[domain]
        if lock.locked():
            raise ScoringFailure(503, "Model capacity exhausted")
        async with lock:
            circuit = self.circuits[domain]
            if circuit.opened_at is not None:
                if time.monotonic() - circuit.opened_at < self.settings.model_cooldown_seconds:
                    raise ScoringFailure(503, "Model circuit is open")
            adapter = self.models.get(domain)
            if not adapter.availability().available:
                raise ModelUnavailable(
                    "Authoritative model, preprocessing, and inference contract not yet verified"
                )
            try:
                async with asyncio.timeout(self.settings.model_timeout_seconds):
                    raw = await adapter.score(request)
                # Dump an existing model too: do not trust unchecked model_construct() values.
                payload = raw.model_dump(warnings=False) if isinstance(raw, ScoreResult) else raw
                result = ScoreResult.model_validate(payload)
                if (
                    result.domain != domain
                    or result.input_schema_version != request.input_schema_version
                ):
                    raise ValueError("Mismatched model contract")
            except Exception as error:
                circuit.failures += 1
                if circuit.failures >= self.settings.model_failure_threshold:
                    circuit.opened_at = time.monotonic()
                status = 504 if isinstance(error, TimeoutError) else 502
                raise ScoringFailure(status, "Model execution failed safely") from None
            circuit.failures = 0
            circuit.opened_at = None
            return result

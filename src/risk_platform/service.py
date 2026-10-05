import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from risk_platform.contracts import (
    CaseCreate,
    Domain,
    EvidenceCreate,
    ModelAvailability,
    ScoreRequest,
    ScoreResult,
)
from risk_platform.database import AuditEvent, Case, EvidenceReference, ModelScoreReference


class DomainDenied(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class CaseNotFound(Exception):
    pass


class CaseService:
    def __init__(self, session: AsyncSession, actor_id: str, domains: set[str] | None = None):
        self.session = session
        self.actor_id = actor_id
        self.domains = frozenset(Domain if domains is None else domains)

    async def create(self, request: CaseCreate, key: str) -> tuple[Case, bool]:
        if request.domain not in self.domains:
            raise DomainDenied()
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        lookup = select(Case).where(Case.owner_id == self.actor_id, Case.idempotency_key == key)
        existing = await self.session.scalar(lookup)
        if existing:
            return self._replay(existing, fingerprint), False
        case = Case(
            owner_id=self.actor_id, idempotency_key=key, request_hash=fingerprint, **payload
        )
        self.session.add(case)
        try:
            await self.session.flush()
            self.session.add(
                AuditEvent(case_id=case.id, actor_id=self.actor_id, event="case.created")
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            # A concurrent request may have won the unique-key race.
            existing = await self.session.scalar(lookup)
            if existing is None:
                raise
            return self._replay(existing, fingerprint), False
        return case, True

    @staticmethod
    def _replay(case: Case, fingerprint: str) -> Case:
        if case.request_hash != fingerprint:
            raise IdempotencyConflict("Idempotency key was already used for a different request")
        return case

    async def get(self, case_id: UUID) -> Case | None:
        return await self.session.scalar(
            select(Case).where(
                Case.id == case_id, Case.owner_id == self.actor_id, Case.domain.in_(self.domains)
            )
        )

    async def list_cases(self, limit: int, offset: int) -> list[Case]:
        result = await self.session.scalars(
            select(Case)
            .where(Case.owner_id == self.actor_id, Case.domain.in_(self.domains))
            .order_by(Case.created_at.desc(), Case.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def audit(self, case_id: UUID, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        result = await self.session.scalars(
            select(AuditEvent)
            .join(Case, AuditEvent.case_id == Case.id)
            .where(
                Case.id == case_id, Case.owner_id == self.actor_id, Case.domain.in_(self.domains)
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    @staticmethod
    def score_request_hash(domain: Domain, request: ScoreRequest) -> str:
        payload = {"domain": domain, **request.model_dump(mode="json")}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def score_replay(
        self, case_id: UUID, key: str, request_hash: str
    ) -> ModelScoreReference | None:
        score = await self.session.scalar(
            select(ModelScoreReference).where(
                ModelScoreReference.case_id == case_id,
                ModelScoreReference.idempotency_key == key,
            )
        )
        if score is not None and score.request_hash != request_hash:
            raise IdempotencyConflict("Idempotency key was already used for a different request")
        return score

    async def record_score(
        self,
        case: Case,
        key: str,
        request_hash: str,
        result: ScoreResult,
        availability: ModelAvailability,
    ) -> tuple[ModelScoreReference, bool]:
        score = ModelScoreReference(
            case_id=case.id,
            actor_id=self.actor_id,
            idempotency_key=key,
            request_hash=request_hash,
            backend=availability.backend,
            artifact_sha256=availability.artifact_sha256,
            **result.model_dump(mode="python"),
        )
        self.session.add(score)
        try:
            await self.session.flush()
            self.session.add(
                AuditEvent(case_id=case.id, actor_id=self.actor_id, event="model.score_recorded")
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.score_replay(case.id, key, request_hash)
            if existing is None:
                raise
            return existing, False
        return score, True

    async def list_scores(self, case_id: UUID) -> list[ModelScoreReference]:
        result = await self.session.scalars(
            select(ModelScoreReference)
            .where(ModelScoreReference.case_id == case_id)
            .order_by(ModelScoreReference.created_at, ModelScoreReference.id)
        )
        return list(result)

    async def add_evidence(
        self, case_id: UUID, request: EvidenceCreate, key: str
    ) -> tuple[EvidenceReference, bool]:
        if await self.get(case_id) is None:
            raise CaseNotFound()
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        lookup = select(EvidenceReference).where(
            EvidenceReference.case_id == case_id, EvidenceReference.idempotency_key == key
        )

        def replay(record: EvidenceReference) -> tuple[EvidenceReference, bool]:
            if record.request_hash != fingerprint:
                raise IdempotencyConflict()
            return record, False

        existing = await self.session.scalar(lookup)
        if existing is not None:
            return replay(existing)
        record = EvidenceReference(
            case_id=case_id,
            actor_id=self.actor_id,
            idempotency_key=key,
            request_hash=fingerprint,
            **payload,
        )
        self.session.add(record)
        try:
            await self.session.flush()
            self.session.add(
                AuditEvent(case_id=case_id, actor_id=self.actor_id, event="evidence.recorded")
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(lookup)
            if existing is None:
                raise
            return replay(existing)
        return record, True

    async def list_evidence(
        self, case_id: UUID, limit: int = 25, offset: int = 0
    ) -> list[EvidenceReference]:
        if await self.get(case_id) is None:
            raise CaseNotFound()
        result = await self.session.scalars(
            select(EvidenceReference)
            .join(Case, EvidenceReference.case_id == Case.id)
            .where(
                Case.id == case_id, Case.owner_id == self.actor_id, Case.domain.in_(self.domains)
            )
            .order_by(EvidenceReference.created_at, EvidenceReference.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from risk_platform.contracts import (
    CaseCreate,
    CaseScoreView,
    Domain,
    EvidenceCreate,
    EvidenceView,
    InvestigationCreate,
    InvestigationRunCreate,
    ModelAvailability,
    ReviewCreate,
    ScoreRequest,
    ScoreResult,
)
from risk_platform.database import (
    AuditEvent,
    Case,
    EvidenceReference,
    InvestigationRecord,
    InvestigationReview,
    InvestigationRun,
    ModelScoreReference,
)


class DomainDenied(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class CaseNotFound(Exception):
    pass


class EvidenceUnavailable(Exception):
    pass


class CaseService:
    def __init__(self, session: AsyncSession, actor_id: str, domains: set[str] | None = None):
        self.session = session
        self.actor_id = actor_id
        self.domains = frozenset(Domain if domains is None else domains)

    @staticmethod
    def fingerprint(request) -> str:
        return hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()

    async def get_review(self, investigation_id: UUID) -> InvestigationReview | None:
        if await self.get_investigation(investigation_id) is None:
            raise CaseNotFound()
        return await self.session.scalar(
            select(InvestigationReview).where(
                InvestigationReview.investigation_id == investigation_id
            )
        )

    async def review_investigation(
        self, investigation_id: UUID, request: ReviewCreate, key: str
    ) -> tuple[InvestigationReview, bool]:
        investigation = await self.get_investigation(investigation_id)
        if investigation is None:
            raise CaseNotFound()
        case_id = investigation.case_id
        fingerprint = self.fingerprint(request)

        def replay(record):
            if record.idempotency_key != key or record.request_hash != fingerprint:
                raise IdempotencyConflict()
            return record, False

        existing = await self.get_review(investigation_id)
        if existing is not None:
            return replay(existing)
        record = InvestigationReview(
            investigation_id=investigation_id,
            actor_id=self.actor_id,
            idempotency_key=key,
            request_hash=fingerprint,
            **request.model_dump(),
        )
        self.session.add(record)
        try:
            await self.session.flush()
            self.session.add(
                AuditEvent(case_id=case_id, actor_id=self.actor_id, event="investigation.reviewed")
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_review(investigation_id)
            if existing is None:
                raise
            return replay(existing)
        return record, True

    async def run_investigation(
        self, case_id: UUID, request: InvestigationRunCreate, key: str
    ) -> tuple[InvestigationRun, bool]:
        # Optional dependency is loaded only when the explicitly enabled endpoint runs.
        from langgraph.checkpoint.memory import InMemorySaver

        from risk_platform.agent_policy import Evidence, InvestigationScope
        from risk_platform.investigation_workflow import InvestigationWorkflow

        case = await self.get(case_id)
        if case is None:
            raise CaseNotFound()
        domain = Domain(case.domain)
        fingerprint = self.fingerprint(request)
        lookup = select(InvestigationRun).where(
            InvestigationRun.case_id == case_id, InvestigationRun.idempotency_key == key
        )

        def replay(record):
            if record.request_hash != fingerprint:
                raise IdempotencyConflict()
            return record, False

        existing = await self.session.scalar(lookup)
        if existing is not None:
            return replay(existing)
        scores = await self.session.scalars(
            select(ModelScoreReference)
            .join(Case, ModelScoreReference.case_id == Case.id)
            .where(
                Case.id == case_id,
                Case.owner_id == self.actor_id,
                Case.domain.in_(self.domains),
                ModelScoreReference.domain == domain,
                ModelScoreReference.id.in_(request.score_ids),
            )
        )
        by_id = {score.id: score for score in scores}
        if len(by_id) != len(request.score_ids):
            raise EvidenceUnavailable()
        snapshots = [
            CaseScoreView.model_validate(by_id[item], from_attributes=True).model_dump(mode="json")
            for item in request.score_ids
        ]
        scope = InvestigationScope(case_id, domain, self.actor_id, self.actor_id)

        async def retrieve(current, arguments):
            # Server-selected immutable score metadata only; never features or source URLs.
            return tuple(
                Evidence(str(item["id"]), case_id, domain, self.actor_id, json.dumps(item))
                for item in snapshots
            )

        packet = await InvestigationWorkflow(
            scope, {"get_case_evidence": retrieve}, InMemorySaver()
        ).run(uuid4(), request.query)
        investigation = InvestigationRecord(
            case_id=case_id,
            actor_id=self.actor_id,
            idempotency_key="workflow:" + uuid4().hex,
            request_hash=fingerprint,
            disposition=packet.recommendation.disposition,
            summary=packet.recommendation.summary,
            evidence=[],
        )
        self.session.add(investigation)
        try:
            await self.session.flush()
            record = InvestigationRun(
                case_id=case_id,
                investigation_id=investigation.id,
                idempotency_key=key,
                request_hash=fingerprint,
                workflow_version="score-review-abstention-v1",
                scores=snapshots,
            )
            self.session.add(record)
            self.session.add(
                AuditEvent(
                    case_id=case_id,
                    actor_id=self.actor_id,
                    event="investigation.workflow_completed",
                )
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(lookup)
            if existing is None:
                raise
            return replay(existing)
        return record, True

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

    async def submit_investigation(
        self, case_id: UUID, request: InvestigationCreate, key: str
    ) -> tuple[InvestigationRecord, bool]:
        if await self.get(case_id) is None:
            raise CaseNotFound()
        fingerprint = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        lookup = select(InvestigationRecord).where(
            InvestigationRecord.case_id == case_id, InvestigationRecord.idempotency_key == key
        )

        def replay(record: InvestigationRecord) -> tuple[InvestigationRecord, bool]:
            if record.request_hash != fingerprint:
                raise IdempotencyConflict()
            return record, False

        existing = await self.session.scalar(lookup)
        if existing is not None:
            return replay(existing)
        references = await self.session.scalars(
            select(EvidenceReference)
            .join(Case, EvidenceReference.case_id == Case.id)
            .where(
                Case.id == case_id,
                Case.owner_id == self.actor_id,
                Case.domain.in_(self.domains),
                EvidenceReference.id.in_(request.evidence_ids),
            )
        )
        by_id = {reference.id: reference for reference in references}
        if len(by_id) != len(request.evidence_ids):
            # Do not reveal whether a missing reference exists in another case.
            raise EvidenceUnavailable()
        record = InvestigationRecord(
            case_id=case_id,
            actor_id=self.actor_id,
            idempotency_key=key,
            request_hash=fingerprint,
            disposition=request.disposition,
            summary=request.summary,
            evidence=[
                EvidenceView.model_validate(by_id[item], from_attributes=True).model_dump(
                    mode="json"
                )
                for item in request.evidence_ids
            ],
        )
        self.session.add(record)
        try:
            await self.session.flush()
            self.session.add(
                AuditEvent(case_id=case_id, actor_id=self.actor_id, event="investigation.submitted")
            )
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(lookup)
            if existing is None:
                raise
            return replay(existing)
        return record, True

    async def get_investigation(self, investigation_id: UUID) -> InvestigationRecord | None:
        return await self.session.scalar(
            select(InvestigationRecord)
            .join(Case, InvestigationRecord.case_id == Case.id)
            .where(
                InvestigationRecord.id == investigation_id,
                Case.owner_id == self.actor_id,
                Case.domain.in_(self.domains),
            )
        )

    async def list_investigations(
        self, case_id: UUID, limit: int = 10, offset: int = 0
    ) -> list[InvestigationRecord]:
        if await self.get(case_id) is None:
            raise CaseNotFound()
        result = await self.session.scalars(
            select(InvestigationRecord)
            .join(Case, InvestigationRecord.case_id == Case.id)
            .where(
                Case.id == case_id, Case.owner_id == self.actor_id, Case.domain.in_(self.domains)
            )
            .order_by(InvestigationRecord.created_at, InvestigationRecord.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

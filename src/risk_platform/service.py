import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from risk_platform.contracts import CaseCreate
from risk_platform.database import AuditEvent, Case


class IdempotencyConflict(Exception):
    pass


class CaseService:
    def __init__(self, session: AsyncSession, actor_id: str):
        self.session = session
        self.actor_id = actor_id

    async def create(self, request: CaseCreate, key: str) -> tuple[Case, bool]:
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
            select(Case).where(Case.id == case_id, Case.owner_id == self.actor_id)
        )

    async def list_cases(self, limit: int, offset: int) -> list[Case]:
        result = await self.session.scalars(
            select(Case)
            .where(Case.owner_id == self.actor_id)
            .order_by(Case.created_at.desc(), Case.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def audit(self, case_id: UUID) -> list[AuditEvent]:
        result = await self.session.scalars(
            select(AuditEvent)
            .join(Case, AuditEvent.case_id == Case.id)
            .where(Case.id == case_id, Case.owner_id == self.actor_id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        )
        return list(result)

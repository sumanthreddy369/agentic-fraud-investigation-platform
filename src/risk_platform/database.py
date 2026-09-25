from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Persist UTC; restore timezone info for SQLite test results."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must have a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    domain: Mapped[str] = mapped_column(String(30))
    source_record_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="open")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(200))
    event: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite+"):
        # Used only by fast local tests; never a production PostgreSQL substitute.
        return create_async_engine(url)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args={"connect_timeout": 5},
    )


def make_sessions(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)

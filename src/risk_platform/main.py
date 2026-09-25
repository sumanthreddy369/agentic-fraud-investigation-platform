import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from risk_platform.adapters import ModelRegistry, ModelUnavailable
from risk_platform.config import Settings
from risk_platform.contracts import (
    AuditView,
    CaseCreate,
    CaseView,
    Domain,
    ModelAvailability,
    ScoreRequest,
    ScoreResult,
)
from risk_platform.database import make_engine, make_sessions
from risk_platform.service import CaseService, IdempotencyConflict

logger = logging.getLogger("risk_platform")
bearer = HTTPBearer(auto_error=False)


async def actor(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    settings: Settings = request.app.state.settings
    token = settings.api_token.get_secret_value()
    if not token:
        raise HTTPException(503, "Local operator access is not configured")
    if credential is None or not secrets.compare_digest(credential.credentials, token):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return settings.operator_id


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as database_session:
        yield database_session


async def service(
    actor_id: Annotated[str, Depends(actor)],
    database_session: Annotated[AsyncSession, Depends(session)],
) -> CaseService:
    return CaseService(database_session, actor_id)


def case_view(case) -> CaseView:
    return CaseView.model_validate(case, from_attributes=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(configuration.database_url.get_secret_value())
        app.state.sessions = make_sessions(engine)
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Risk Investigation Platform", version="0.1.0", lifespan=lifespan)
    app.state.settings = configuration
    app.state.models = ModelRegistry()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        # Generate server-side IDs; never log request bodies, tokens, or raw database errors.
        request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info("request_complete request_id=%s status=%s", request_id, response.status_code)
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready(database_session: Annotated[AsyncSession, Depends(session)]):
        # A socket check alone would report ready before migrations have been applied.
        revision = await database_session.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0001_cases":
            raise HTTPException(503, "Database schema is not current")
        await database_session.execute(text("SELECT id FROM cases LIMIT 0"))
        return {"status": "ready", "scope": "case_api", "models_configured": False}

    @app.get("/v1/models", response_model=list[ModelAvailability])
    async def models(_: Annotated[str, Depends(actor)]):
        return app.state.models.availability()

    @app.post("/v1/models/{domain}/score", response_model=ScoreResult)
    async def score(domain: Domain, payload: ScoreRequest, _: Annotated[str, Depends(actor)]):
        try:
            return await app.state.models.get(domain).score(payload)
        except ModelUnavailable as error:
            raise HTTPException(503, str(error)) from error

    @app.post("/v1/cases", response_model=CaseView, status_code=201)
    async def create_case(
        payload: CaseCreate,
        response: Response,
        cases: Annotated[CaseService, Depends(service)],
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r"^[!-~]+$")],
    ):
        try:
            case, created = await cases.create(payload, idempotency_key)
        except IdempotencyConflict as error:
            raise HTTPException(409, str(error)) from error
        response.status_code = 201 if created else 200
        return case_view(case)

    @app.get("/v1/cases", response_model=list[CaseView])
    async def list_cases(
        cases: Annotated[CaseService, Depends(service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return [case_view(case) for case in await cases.list_cases(limit, offset)]

    @app.get("/v1/cases/{case_id}", response_model=CaseView)
    async def get_case(case_id: UUID, cases: Annotated[CaseService, Depends(service)]):
        case = await cases.get(case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        return case_view(case)

    @app.get("/v1/cases/{case_id}/audit", response_model=list[AuditView])
    async def audit(case_id: UUID, cases: Annotated[CaseService, Depends(service)]):
        if await cases.get(case_id) is None:
            raise HTTPException(404, "Case not found")
        return [
            AuditView.model_validate(event, from_attributes=True)
            for event in await cases.audit(case_id)
        ]

    return app

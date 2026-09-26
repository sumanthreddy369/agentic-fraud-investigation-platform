import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware

from risk_platform.adapters import ModelRegistry, ModelUnavailable
from risk_platform.authorization import require_permission
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
from risk_platform.control_catalog import control_catalog
from risk_platform.database import make_engine, make_sessions
from risk_platform.http_guardrails import GuardrailMiddleware
from risk_platform.onnx_adapter import load_onnx_adapters
from risk_platform.scoring import ScoringFailure, ScoringGateway
from risk_platform.service import CaseService, DomainDenied, IdempotencyConflict

bearer = HTTPBearer(auto_error=False)


async def actor(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    settings: Settings = request.app.state.settings
    token = settings.api_token.get_secret_value()
    if not token:
        raise HTTPException(503, "Local operator access is not configured")
    if credential is None or not secrets.compare_digest(
        credential.credentials.encode(), token.encode()
    ):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return settings.operator_id


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as database_session:
        yield database_session


async def service(
    request: Request,
    actor_id: Annotated[str, Depends(actor)],
    database_session: Annotated[AsyncSession, Depends(session)],
) -> CaseService:
    return CaseService(database_session, actor_id, request.app.state.settings.allowed_domains)


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

    app = FastAPI(
        title="Risk Investigation Platform",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs" if configuration.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if configuration.docs_enabled else None,
    )
    app.state.settings = configuration
    app.state.models = ModelRegistry(load_onnx_adapters(configuration.onnx_manifests))

    app.state.scoring = ScoringGateway(app.state.models, configuration)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=configuration.allowed_hosts)
    app.add_middleware(GuardrailMiddleware, settings=configuration)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # FastAPI's default errors include raw inputs; those can contain PII or credentials.
        errors = [
            {"code": item["type"], "source": str(item["loc"][0])}
            for item in error.errors()[:20]
            if item["loc"]
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": errors,
            },
        )

    @app.exception_handler(DomainDenied)
    async def domain_error(request: Request, error: DomainDenied):
        return JSONResponse(status_code=403, content={"detail": "Domain access denied"})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
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
    async def models(_: Annotated[str, Depends(require_permission("models:read", actor))]):
        return [
            item
            for item in app.state.models.availability()
            if item.domain in configuration.allowed_domains
        ]

    @app.post("/v1/models/{domain}/score", response_model=ScoreResult)
    async def score(
        domain: Domain,
        payload: ScoreRequest,
        _: Annotated[str, Depends(require_permission("models:score", actor))],
    ):
        if domain not in configuration.allowed_domains:
            raise HTTPException(403, "Domain access denied")
        try:
            return await app.state.scoring.score(domain, payload)
        except ModelUnavailable as error:
            raise HTTPException(503, str(error)) from error
        except ScoringFailure as error:
            raise HTTPException(error.status, error.reason) from None

    @app.post(
        "/v1/cases",
        response_model=CaseView,
        status_code=201,
        dependencies=[Depends(require_permission("cases:create", actor))],
    )
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

    @app.get(
        "/v1/cases",
        response_model=list[CaseView],
        dependencies=[Depends(require_permission("cases:read", actor))],
    )
    async def list_cases(
        cases: Annotated[CaseService, Depends(service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    ):
        return [case_view(case) for case in await cases.list_cases(limit, offset)]

    @app.get(
        "/v1/cases/{case_id}",
        response_model=CaseView,
        dependencies=[Depends(require_permission("cases:read", actor))],
    )
    async def get_case(case_id: UUID, cases: Annotated[CaseService, Depends(service)]):
        case = await cases.get(case_id)
        if case is None:
            raise HTTPException(404, "Case not found")
        return case_view(case)

    @app.get(
        "/v1/cases/{case_id}/audit",
        response_model=list[AuditView],
        dependencies=[Depends(require_permission("audit:read", actor))],
    )
    async def audit(
        case_id: UUID,
        cases: Annotated[CaseService, Depends(service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    ):
        if await cases.get(case_id) is None:
            raise HTTPException(404, "Case not found")
        return [
            AuditView.model_validate(event, from_attributes=True)
            for event in await cases.audit(case_id, limit, offset)
        ]

    @app.get("/v1/guardrails", dependencies=[Depends(require_permission("controls:read", actor))])
    async def controls():
        return control_catalog(configuration)

    return app

import pytest
from httpx import ASGITransport, AsyncClient

from risk_platform.config import Settings
from risk_platform.contracts import Domain, ModelAvailability, ScoreResult
from risk_platform.main import actor, create_app

PAYLOAD = {"domain": "ieee_cis", "source_record_id": "transaction-123", "title": "Review alert"}


async def test_case_persists_and_replay_has_one_audit_event(client):
    api, app = client
    first = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "create-1"})
    assert first.status_code == 201
    case = first.json()
    replay = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "create-1"})
    assert replay.status_code == 200
    assert replay.json()["id"] == case["id"]
    assert (await api.get(f"/v1/cases/{case['id']}")).json() == case
    assert (await api.get("/v1/cases")).json() == [case]
    audit = (await api.get(f"/v1/cases/{case['id']}/audit")).json()
    assert [event["event"] for event in audit] == ["case.created"]
    assert audit[0]["actor_id"] == "local-investigator"
    # Recreate the application to verify the state is not held in process memory.
    restarted = create_app(app.state.settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test", headers=api.headers
        ) as second:
            assert (await second.get(f"/v1/cases/{case['id']}")).json() == case


async def test_idempotency_key_cannot_change_payload(client):
    api, _ = client
    await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "same"})
    response = await api.post(
        "/v1/cases",
        json={**PAYLOAD, "domain": "home_credit"},
        headers={"Idempotency-Key": "same"},
    )
    assert response.status_code == 409
    assert len((await api.get("/v1/cases")).json()) == 1


async def test_other_identity_cannot_read_case_or_audit(client):
    api, app = client
    response = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "owner"})
    case_id = response.json()["id"]
    app.dependency_overrides[actor] = lambda: "other-investigator"
    assert (await api.get(f"/v1/cases/{case_id}")).status_code == 404
    assert (await api.get(f"/v1/cases/{case_id}/audit")).status_code == 404
    assert (await api.get("/v1/cases")).json() == []


@pytest.mark.parametrize("domain", ["ieee_cis", "home_credit", "elliptic"])
async def test_unverified_models_never_generate_scores(client, domain):
    api, _ = client
    response = await api.post(
        f"/v1/models/{domain}/score", json={"input_schema_version": "unknown", "features": {}}
    )
    assert response.status_code == 503
    assert "probability" not in response.json()
    assert "not yet verified" in response.json()["detail"]


async def test_inventory_has_all_domains(client):
    api, _ = client
    models = (await api.get("/v1/models")).json()
    assert {model["domain"] for model in models} == {"ieee_cis", "home_credit", "elliptic"}
    assert all(model["available"] is False for model in models)


class ProvenanceAdapter:
    def __init__(self):
        self.calls = 0

    def availability(self):
        return ModelAvailability(
            domain=Domain.TRANSACTION,
            available=True,
            reason="verified fixture",
            backend="fixture-runtime",
            model_version="fixture-v1",
            artifact_sha256="a" * 64,
        )

    async def score(self, request):
        self.calls += 1
        return ScoreResult(
            domain=Domain.TRANSACTION,
            model_version="fixture-v1",
            input_schema_version=request.input_schema_version,
            positive_class="fraud",
            probability=0.82,
        )


async def test_case_score_provenance_is_immutable_idempotent_and_feature_safe(client):
    api, app = client
    created = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "score-case"})
    case_id = created.json()["id"]
    adapter = ProvenanceAdapter()
    app.state.models._adapters[Domain.TRANSACTION] = adapter
    request = {"input_schema_version": "v1", "features": {"amount": 123.45}}
    first = await api.post(
        f"/v1/cases/{case_id}/scores",
        json=request,
        headers={"Idempotency-Key": "score-1"},
    )
    assert first.status_code == 201
    score = first.json()
    assert score["case_id"] == case_id
    assert score["probability"] == 0.82
    assert score["backend"] == "fixture-runtime"
    assert score["artifact_sha256"] == "a" * 64
    assert "features" not in score

    replay = await api.post(
        f"/v1/cases/{case_id}/scores",
        json=request,
        headers={"Idempotency-Key": "score-1"},
    )
    assert replay.status_code == 200
    assert replay.json() == score
    assert adapter.calls == 1
    conflict = await api.post(
        f"/v1/cases/{case_id}/scores",
        json={**request, "features": {"amount": 999}},
        headers={"Idempotency-Key": "score-1"},
    )
    assert conflict.status_code == 409
    assert adapter.calls == 1
    assert (await api.get(f"/v1/cases/{case_id}/scores")).json() == [score]
    audit = (await api.get(f"/v1/cases/{case_id}/audit")).json()
    assert [event["event"] for event in audit] == ["case.created", "model.score_recorded"]

    app.dependency_overrides[actor] = lambda: "other-investigator"
    assert (await api.get(f"/v1/cases/{case_id}/scores")).status_code == 404
    assert (
        await api.post(
            f"/v1/cases/{case_id}/scores",
            json=request,
            headers={"Idempotency-Key": "other"},
        )
    ).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {**PAYLOAD, "domain": "invented"},
        {**PAYLOAD, "title": "   "},
        {**PAYLOAD, "source_record_id": ""},
        {**PAYLOAD, "owner_id": "admin"},
    ],
)
async def test_invalid_case_payloads(client, payload):
    api, _ = client
    response = await api.post("/v1/cases", json=payload, headers={"Idempotency-Key": "bad"})
    assert response.status_code == 422
    assert (await api.get("/v1/cases")).json() == []


async def test_authentication_and_disabled_access(client):
    api, app = client
    api.headers.pop("Authorization")
    assert (await api.get("/v1/cases")).status_code == 401
    api.headers["Authorization"] = "Bearer invalid"
    assert (await api.get("/v1/models")).status_code == 401
    from pydantic import SecretStr

    app.state.settings.api_token = SecretStr("")
    assert (await api.get("/v1/cases")).status_code == 503


async def test_health_and_request_id(client):
    api, _ = client
    response = await api.get("/health/live")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert (await api.get("/health/ready")).json()["scope"] == "case_api"


async def test_missing_migration_is_not_ready(tmp_path):
    app = create_app(
        Settings(_env_file=None, database_url=f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            assert (await api.get("/health/live")).status_code == 200
            response = await api.get("/health/ready")
            assert response.status_code == 503
            assert response.json() == {"detail": "Database unavailable"}


def test_shared_environment_and_weak_tokens_are_rejected():
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValueError):
        Settings(_env_file=None, api_token="short")

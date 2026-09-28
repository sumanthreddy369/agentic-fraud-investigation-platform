import asyncio
import json
import logging
import time

import pytest
from pydantic import SecretStr

from risk_platform.contracts import Domain, ModelAvailability, ScoreResult

PAYLOAD = {"domain": "ieee_cis", "source_record_id": "synthetic-1", "title": "Guardrail demo"}


async def test_read_only_roles_and_spoofed_role_header(client):
    api, app = client
    app.state.settings.operator_role = "investigator"
    created = await api.post(
        "/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "existing-case"}
    )
    case_id = created.json()["id"]
    app.state.settings.operator_role = "auditor"
    response = await api.post(
        "/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "one", "X-Role": "admin"}
    )
    assert response.status_code == 403
    assert [item["id"] for item in (await api.get("/v1/cases")).json()] == [case_id]
    response = await api.post(
        "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": {}}
    )
    assert response.status_code == 403
    response = await api.post(
        f"/v1/cases/{case_id}/scores",
        json={"input_schema_version": "v1", "features": {}},
        headers={"Idempotency-Key": "forbidden-score"},
    )
    assert response.status_code == 403


async def test_domain_restriction_hides_existing_case_and_audit(client):
    api, app = client
    created = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "one"})
    case_id = created.json()["id"]
    app.state.settings.allowed_domains = {"elliptic"}
    assert (await api.get(f"/v1/cases/{case_id}")).status_code == 404
    assert (await api.get(f"/v1/cases/{case_id}/audit")).status_code == 404
    assert (await api.get("/v1/cases")).json() == []
    assert (
        await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "two"})
    ).status_code == 403
    assert {item["domain"] for item in (await api.get("/v1/models")).json()} == {"elliptic"}
    app.state.settings.allowed_domains = set()
    assert (await api.get("/v1/models")).json() == []


async def test_kill_switches(client):
    api, app = client
    created = await api.post(
        "/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "existing-case"}
    )
    case_id = created.json()["id"]
    app.state.settings.writes_enabled = False
    app.state.settings.scoring_enabled = False
    assert (
        await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "one"})
    ).status_code == 503
    assert (
        await api.post(
            "/v1/models/elliptic/score", json={"input_schema_version": "v1", "features": {}}
        )
    ).status_code == 503
    assert (
        await api.post(
            f"/v1/cases/{case_id}/scores",
            json={"input_schema_version": "v1", "features": {}},
            headers={"Idempotency-Key": "disabled-score"},
        )
    ).status_code == 503
    assert (await api.get("/v1/cases")).status_code == 200


async def test_oversized_declared_and_chunked_body(client):
    api, app = client
    size = app.state.settings.max_body_bytes
    assert (
        await api.post(
            "/v1/cases", content=b"x" * (size + 1), headers={"Content-Type": "application/json"}
        )
    ).status_code == 413

    async def stream():
        yield b"x" * (size // 2)
        yield b"x" * (size // 2 + 1)

    assert (
        await api.post("/v1/cases", content=stream(), headers={"Content-Type": "application/json"})
    ).status_code == 413
    # Understating Content-Length does not bypass the actual-byte counter.
    assert (
        await api.post(
            "/v1/cases",
            content=b"x" * (size + 1),
            headers={"Content-Type": "application/json", "Content-Length": "1"},
        )
    ).status_code == 413


async def test_content_type_encoding_headers_and_host(client):
    api, _ = client
    assert (await api.post("/v1/cases", content="plain text")).status_code == 415
    assert (
        await api.post("/v1/cases", json=PAYLOAD, headers={"Content-Encoding": "gzip"})
    ).status_code == 415
    assert (await api.get("/v1/cases", headers={"X-Huge": "x" * 17000})).status_code == 431
    assert (await api.get("/v1/cases", headers={"Host": "attacker.example"})).status_code == 400


async def test_rate_limit_ignores_forwarded_peer(client):
    api, app = client
    app.state.settings.requests_per_minute = 2
    assert (await api.get("/v1/models")).status_code == 200
    assert (
        await api.get("/v1/models", headers={"X-Forwarded-For": "192.0.2.1"})
    ).status_code == 200
    response = await api.get("/v1/models", headers={"X-Forwarded-For": "192.0.2.2"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


async def test_concurrency_limit_does_not_queue_unbounded_work(client):
    api, app = client
    app.state.settings.max_concurrent_requests = 1
    entered, release = asyncio.Event(), asyncio.Event()

    @app.get("/test/slow")
    async def slow():
        entered.set()
        await release.wait()
        return {"done": True}

    first = asyncio.create_task(api.get("/test/slow"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await api.get("/v1/models")).status_code == 503
    finally:
        release.set()
        assert (await first).status_code == 200
    assert (await api.get("/v1/models")).status_code == 200


async def test_body_deadline(client):
    api, app = client
    app.state.settings.body_timeout_seconds = 0.01

    async def slow_body():
        await asyncio.sleep(1)
        yield b"{}"

    response = await api.post(
        "/v1/cases", content=slow_body(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 408


async def test_errors_and_logs_do_not_echo_secrets(client, caplog):
    api, app = client
    marker = "private-person@example.test"
    with caplog.at_level(logging.INFO, logger="risk_platform.security"):
        response = await api.post(
            "/v1/cases", json={**PAYLOAD, "domain": marker}, headers={"Idempotency-Key": "one"}
        )
        assert response.status_code == 422
        assert marker not in response.text

        @app.get("/test/crash")
        async def crash():
            raise RuntimeError(marker)

        response = await api.get("/test/crash?secret=" + marker)
        assert response.status_code == 500
        assert marker not in response.text
    assert marker not in caplog.text
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "risk_platform.security"
    ]
    assert {event["status"] for event in events} == {422, 500}
    assert all("request_id" in event for event in events)


async def test_security_headers_on_denials_and_success(client):
    api, _ = client
    for response in (
        await api.get("/v1/models"),
        await api.get("/v1/models", headers={"Authorization": "Bearer invalid"}),
    ):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Request-ID"]


async def test_catalog_is_authenticated_and_honest(client):
    api, app = client
    response = await api.get("/v1/guardrails")
    assert response.status_code == 200
    assert response.json()["enterprise_ready"] is False
    assert app.state.settings.api_token.get_secret_value() not in response.text
    api.headers["Authorization"] = "Bearer invalid"
    assert (await api.get("/v1/guardrails")).status_code == 401
    # Unicode in credentials cannot trigger compare_digest's ASCII-only string failure.
    app.state.settings.api_token = SecretStr("a" * 31 + "é")
    assert (await api.get("/v1/guardrails")).status_code == 401


@pytest.mark.parametrize(
    "features", [{"x": [1, 2]}, {"x": "y" * 1025}, {"bad key": 1}, {f"f{i}": i for i in range(513)}]
)
async def test_feature_payload_bounds(client, features):
    api, _ = client
    response = await api.post(
        "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": features}
    )
    assert response.status_code == 422


class FakeAdapter:
    def __init__(self, result=None, error=None, delay=0):
        self.result, self.error, self.delay = result, error, delay
        self.calls = 0

    def availability(self):
        return ModelAvailability(
            domain=Domain.TRANSACTION,
            available=True,
            reason="test fixture",
            model_version="fixture-v1",
        )

    async def score(self, request):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def result(**changes):
    return {
        "domain": "ieee_cis",
        "model_version": "fixture-v1",
        "input_schema_version": "v1",
        "positive_class": "fraud",
        "probability": 0.8,
        **changes,
    }


@pytest.mark.parametrize(
    "output",
    [
        result(probability=float("nan")),
        result(probability=2),
        result(domain="home_credit"),
        result(input_schema_version="other"),
        result(model_version="fixture-v2"),
        ScoreResult.model_construct(**result(probability=-1)),
    ],
)
async def test_invalid_model_outputs_never_escape(client, output):
    api, app = client
    app.state.models._adapters[Domain.TRANSACTION] = FakeAdapter(result=output)
    response = await api.post(
        "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": {}}
    )
    assert response.status_code == 502
    assert "probability" not in response.json()


async def test_model_timeout_and_circuit_recovery(client):
    api, app = client
    app.state.settings.model_timeout_seconds = 0.01
    app.state.settings.model_failure_threshold = 2
    adapter = FakeAdapter(delay=1)
    app.state.models._adapters[Domain.TRANSACTION] = adapter

    async def score():
        return await api.post(
            "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": {}}
        )

    assert (await score()).status_code == 504
    assert (await score()).status_code == 504
    assert (await score()).status_code == 503
    assert adapter.calls == 2
    circuit = app.state.scoring.circuits[Domain.TRANSACTION]
    circuit.opened_at = time.monotonic() - app.state.settings.model_cooldown_seconds - 1
    adapter.delay, adapter.result = 0, result()
    assert (await score()).status_code == 200
    assert circuit.opened_at is None


async def test_model_error_text_is_not_exposed(client):
    api, app = client
    app.state.models._adapters[Domain.TRANSACTION] = FakeAdapter(error=RuntimeError("secret-key"))
    response = await api.post(
        "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": {}}
    )
    assert response.status_code == 502
    assert "secret-key" not in response.text


async def test_nonfinite_input_and_audit_pagination(client):
    api, _ = client
    response = await api.post(
        "/v1/models/ieee_cis/score",
        content='{"input_schema_version":"v1","features":{"x":NaN}}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    created = await api.post("/v1/cases", json=PAYLOAD, headers={"Idempotency-Key": "audit"})
    case_id = created.json()["id"]
    assert len((await api.get(f"/v1/cases/{case_id}/audit?limit=1")).json()) == 1
    assert (await api.get(f"/v1/cases/{case_id}/audit?offset=1")).json() == []
    assert (await api.get(f"/v1/cases/{case_id}/audit?limit=1000")).status_code == 422


async def test_model_call_capacity(client):
    api, app = client
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingAdapter(FakeAdapter):
        async def score(self, request):
            entered.set()
            await release.wait()
            return result()

    app.state.models._adapters[Domain.TRANSACTION] = WaitingAdapter()

    async def score():
        return await api.post(
            "/v1/models/ieee_cis/score", json={"input_schema_version": "v1", "features": {}}
        )

    task = asyncio.create_task(score())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await score()).status_code == 503
    finally:
        release.set()
        assert (await task).status_code == 200

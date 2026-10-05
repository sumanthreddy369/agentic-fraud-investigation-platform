from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from risk_platform.database import AuditEvent, EvidenceReference
from risk_platform.main import actor, create_app

PAYLOAD = {"source_id": "synthetic-policy", "source_version": "v1", "content_sha256": "a" * 64}


async def make_case(api, key="case"):
    response = await api.post(
        "/v1/cases",
        json={"domain": "ieee_cis", "source_record_id": "synthetic-1", "title": "Evidence test"},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_evidence_replay_conflict_pagination_and_restart(client):
    api, app = client
    case_id = await make_case(api)
    path = f"/v1/cases/{case_id}/evidence"
    headers = {"Idempotency-Key": "evidence-1"}
    first = await api.post(path, json=PAYLOAD, headers=headers)
    assert first.status_code == 201
    record = first.json()
    assert record["actor_id"] == "local-investigator"
    assert record["case_id"] == case_id
    assert "request_hash" not in record and "idempotency_key" not in record
    replay = await api.post(path, json=PAYLOAD, headers=headers)
    assert replay.status_code == 200 and replay.json() == record
    conflict = await api.post(path, json={**PAYLOAD, "content_sha256": "b" * 64}, headers=headers)
    assert conflict.status_code == 409
    assert (await api.get(path)).json() == [record]
    assert (await api.get(path + "?offset=1&limit=1")).json() == []
    for query in ("limit=101", "offset=10001", "limit=0", "offset=-1"):
        assert (await api.get(path + "?" + query)).status_code == 422
    audit = (await api.get(f"/v1/cases/{case_id}/audit")).json()
    assert [event["event"] for event in audit] == ["case.created", "evidence.recorded"]
    restarted = create_app(app.state.settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test", headers=api.headers
        ) as second:
            assert (await second.get(path)).json() == [record]
    other = await make_case(api, "other-case")
    assert (
        await api.post(f"/v1/cases/{other}/evidence", json=PAYLOAD, headers=headers)
    ).status_code == 201


@pytest.mark.parametrize("restriction", ["owner", "domain", "missing"])
async def test_evidence_scope_denies_reads_and_writes(client, restriction):
    api, app = client
    case_id = await make_case(api)
    if restriction == "owner":
        app.dependency_overrides[actor] = lambda: "other-owner"
    elif restriction == "domain":
        app.state.settings.allowed_domains = {"elliptic"}
    else:
        case_id = uuid4()
    path = f"/v1/cases/{case_id}/evidence"
    assert (await api.get(path)).status_code == 404
    assert (await api.post(path, json=PAYLOAD, headers={"Idempotency-Key": "e"})).status_code == 404
    async with app.state.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceReference)) == 0


@pytest.mark.parametrize("role", ["reviewer", "auditor"])
async def test_evidence_read_only_roles(client, role):
    api, app = client
    case_id = await make_case(api)
    app.state.settings.operator_role = role
    path = f"/v1/cases/{case_id}/evidence"
    assert (await api.get(path)).status_code == 200
    response = await api.post(
        path, json=PAYLOAD, headers={"Idempotency-Key": "e", "X-Role": "investigator"}
    )
    assert response.status_code == 403


async def test_evidence_kill_switch_and_authentication(client):
    api, app = client
    case_id = await make_case(api)
    path = f"/v1/cases/{case_id}/evidence"
    app.state.settings.writes_enabled = False
    assert (await api.post(path, json=PAYLOAD, headers={"Idempotency-Key": "e"})).status_code == 503
    assert (await api.get(path)).status_code == 200
    api.headers.pop("Authorization")
    assert (await api.get(path)).status_code == 401
    assert (await api.post(path, json=PAYLOAD, headers={"Idempotency-Key": "e"})).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": "https://untrusted.invalid/private"},
        {"source_id": ""},
        {"source_id": "x" * 201},
        {"source_version": "x" * 129},
        {"source_version": 1},
        {"content_sha256": "invalid"},
        {"content_sha256": "A" * 64},
        {"excerpt": "private text"},
        {"actor_id": "spoofed"},
        {"domain": "elliptic"},
    ],
)
async def test_evidence_contract_rejects_invalid_or_unrequested_content(client, changes):
    api, app = client
    case_id = await make_case(api)
    response = await api.post(
        f"/v1/cases/{case_id}/evidence",
        json={**PAYLOAD, **changes},
        headers={"Idempotency-Key": "e"},
    )
    assert response.status_code == 422
    async with app.state.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(EvidenceReference)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 1

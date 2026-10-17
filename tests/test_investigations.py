from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from risk_platform.main import actor, create_app


async def setup_case(api, key="case", domain="ieee_cis"):
    response = await api.post(
        "/v1/cases",
        headers={"Idempotency-Key": key},
        json={"domain": domain, "source_record_id": "synthetic", "title": "Synthetic case"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]
    reference = await api.post(
        f"/v1/cases/{case_id}/evidence",
        headers={"Idempotency-Key": "evidence"},
        json={"source_id": "synthetic", "source_version": "v1", "content_sha256": "a" * 64},
    )
    assert reference.status_code == 201
    return case_id, reference.json()


def proposal(evidence):
    return {
        "disposition": "escalate",
        "summary": "Synthetic recommendation",
        "evidence_ids": [evidence["id"]],
    }


async def test_investigation_snapshot_replay_restart_and_bounds(client, caplog):
    api, app = client
    case_id, evidence = await setup_case(api)
    path = f"/v1/cases/{case_id}/investigations"
    payload = proposal(evidence)
    payload["summary"] = "private-summary-marker"
    first = await api.post(path, json=payload, headers={"Idempotency-Key": "run"})
    assert first.status_code == 201
    record = first.json()
    assert record["evidence"] == [evidence]
    assert record["status"] == "awaiting_review" and record["requires_human_review"] is True
    assert record["actor_id"] == "local-investigator"
    assert "request_hash" not in record
    replay = await api.post(path, json=payload, headers={"Idempotency-Key": "run"})
    assert replay.status_code == 200 and replay.json() == record
    conflict = await api.post(
        path, json={**payload, "summary": "Changed"}, headers={"Idempotency-Key": "run"}
    )
    assert conflict.status_code == 409
    assert (await api.get(path)).json() == [record]
    assert (await api.get(path + "?limit=1&offset=1")).json() == []
    for query in ("limit=26", "limit=0", "offset=-1", "offset=10001"):
        assert (await api.get(path + "?" + query)).status_code == 422
    audit = (await api.get(f"/v1/cases/{case_id}/audit")).json()
    assert [item["event"] for item in audit] == [
        "case.created",
        "evidence.recorded",
        "investigation.submitted",
    ]
    # Later evidence does not alter the stored snapshot or replay result.
    await api.post(
        f"/v1/cases/{case_id}/evidence",
        headers={"Idempotency-Key": "new-version"},
        json={"source_id": "synthetic", "source_version": "v2", "content_sha256": "b" * 64},
    )
    restarted = create_app(app.state.settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test", headers=api.headers
        ) as second:
            assert (await second.get(f"/v1/investigations/{record['id']}")).json() == record
            assert (
                await second.post(path, json=payload, headers={"Idempotency-Key": "run"})
            ).json() == record
    assert "private-summary-marker" not in caplog.text
    assert (await api.get(f"/v1/cases/{case_id}")).json()["status"] == "open"


@pytest.mark.parametrize("domain", ["ieee_cis", "home_credit", "elliptic"])
async def test_investigation_empty_evidence_only_allows_abstention(client, domain):
    api, _ = client
    case_id, _ = await setup_case(api, domain=domain)
    path = f"/v1/cases/{case_id}/investigations"
    for disposition in ("escalate", "no_further_action"):
        response = await api.post(
            path,
            headers={"Idempotency-Key": "run"},
            json={
                "disposition": disposition,
                "summary": "Synthetic",
                "evidence_ids": [],
            },
        )
        assert response.status_code == 422
    response = await api.post(
        path,
        headers={"Idempotency-Key": "run"},
        json={
            "disposition": "insufficient_evidence",
            "summary": "No evidence available",
            "evidence_ids": [],
        },
    )
    assert response.status_code == 201 and response.json()["requires_human_review"] is True


@pytest.mark.parametrize("kind", ["other-case", "other-domain", "unknown"])
async def test_investigation_rejects_unscoped_citations_without_writes(client, kind):
    api, _ = client
    case_id, _ = await setup_case(api)
    _, other = await setup_case(api, "other", "elliptic" if kind == "other-domain" else "ieee_cis")
    if kind == "unknown":
        other["id"] = str(uuid4())
    response = await api.post(
        f"/v1/cases/{case_id}/investigations",
        json=proposal(other),
        headers={"Idempotency-Key": "run"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Evidence references are unavailable for this case"
    assert (await api.get(f"/v1/cases/{case_id}/investigations")).json() == []
    assert len((await api.get(f"/v1/cases/{case_id}/audit")).json()) == 2


@pytest.mark.parametrize("restriction", ["owner", "domain"])
async def test_investigation_access_is_scoped_on_every_route(client, restriction):
    api, app = client
    case_id, evidence = await setup_case(api)
    path = f"/v1/cases/{case_id}/investigations"
    first = await api.post(path, json=proposal(evidence), headers={"Idempotency-Key": "run"})
    if restriction == "owner":
        app.dependency_overrides[actor] = lambda: "other-owner"
    else:
        app.state.settings.allowed_domains = {"elliptic"}
    assert (await api.get(path)).status_code == 404
    assert (await api.get(f"/v1/investigations/{first.json()['id']}")).status_code == 404
    assert (
        await api.post(path, json=proposal(evidence), headers={"Idempotency-Key": "run"})
    ).status_code == 404


@pytest.mark.parametrize("role", ["reviewer", "auditor"])
async def test_investigation_permissions_and_kill_switch(client, role):
    api, app = client
    case_id, evidence = await setup_case(api)
    path = f"/v1/cases/{case_id}/investigations"
    app.state.settings.operator_role = role
    response = await api.post(
        path, json=proposal(evidence), headers={"Idempotency-Key": "run", "X-Role": "investigator"}
    )
    assert response.status_code == 403
    assert (await api.get(path)).status_code == 200
    app.state.settings.operator_role = "investigator"
    app.state.settings.writes_enabled = False
    assert (
        await api.post(path, json=proposal(evidence), headers={"Idempotency-Key": "run"})
    ).status_code == 503
    api.headers.pop("Authorization")
    assert (await api.get(path)).status_code == 401
    assert (await api.get(f"/v1/investigations/{uuid4()}")).status_code == 401
    assert (
        await api.post(path, json=proposal(evidence), headers={"Idempotency-Key": "run"})
    ).status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        {"status": "approved"},
        {"requires_human_review": False},
        {"actor_id": "spoofed"},
        {"domain": "elliptic"},
        {"summary": " "},
        {"summary": "x" * 4001},
        {"disposition": "block_account"},
        {"evidence_ids": [str(uuid4()) for _ in range(21)]},
        {"evidence_ids": ["not-a-uuid"]},
        {"evidence": []},
    ],
)
async def test_investigation_strict_contract(client, change):
    api, _ = client
    case_id, evidence = await setup_case(api)
    response = await api.post(
        f"/v1/cases/{case_id}/investigations",
        json={**proposal(evidence), **change},
        headers={"Idempotency-Key": "run"},
    )
    assert response.status_code == 422


async def test_duplicate_citations_and_missing_resources(client):
    api, _ = client
    case_id, evidence = await setup_case(api)
    payload = proposal(evidence)
    payload["evidence_ids"] *= 2
    assert (
        await api.post(
            f"/v1/cases/{case_id}/investigations", json=payload, headers={"Idempotency-Key": "run"}
        )
    ).status_code == 422
    assert (await api.get(f"/v1/investigations/{uuid4()}")).status_code == 404
    assert (await api.get(f"/v1/cases/{uuid4()}/investigations")).status_code == 404
    assert (
        await api.post(
            f"/v1/cases/{uuid4()}/investigations",
            json=proposal(evidence),
            headers={"Idempotency-Key": "run"},
        )
    ).status_code == 404

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from risk_platform.contracts import CaseCreate, Domain, ModelAvailability, ScoreResult
from risk_platform.main import actor, create_app
from risk_platform.service import CaseService

pytest.importorskip("langgraph")


async def seed(app):
    async with app.state.sessions() as session:
        service = CaseService(session, "local-investigator")
        case, _ = await service.create(
            CaseCreate(domain=Domain.TRANSACTION, source_record_id="synthetic", title="Test"),
            str(uuid4()),
        )
        score, _ = await service.record_score(
            case,
            "score",
            "a" * 64,
            ScoreResult(
                domain=Domain.TRANSACTION,
                model_version="fixture",
                input_schema_version="v1",
                positive_class="fraud",
                probability=0.8,
            ),
            ModelAvailability(
                domain=Domain.TRANSACTION,
                available=True,
                reason="fixture",
                backend="fixture",
                artifact_sha256="b" * 64,
            ),
        )
        return case.id, score.id


async def test_run_review_restart_and_audit(client):
    api, app = client
    case_id, score_id = await seed(app)
    path = f"/v1/cases/{case_id}/investigation-runs"
    payload = {"query": "sensitive-query-marker", "score_ids": [str(score_id)]}
    headers = {"Idempotency-Key": "run"}
    assert (await api.post(path, json=payload, headers=headers)).status_code == 503
    app.state.settings.investigations_enabled = True
    first = await api.post(path, json=payload, headers=headers)
    assert first.status_code == 201
    run = first.json()
    assert run["scores"][0]["id"] == str(score_id)
    assert "features" not in run["scores"][0]
    investigation_path = f"/v1/investigations/{run['investigation_id']}"
    original = (await api.get(investigation_path)).json()
    assert original["disposition"] == "insufficient_evidence"
    assert original["requires_human_review"] is True
    review_path = investigation_path + "/review"
    review = {"decision": "request_changes", "rationale": "Additional evidence needed"}
    assert (await api.post(review_path, json=review, headers=headers)).status_code == 403
    app.state.settings.operator_role = "reviewer"
    accepted = await api.post(review_path, json=review, headers=headers)
    assert accepted.status_code == 201
    assert (await api.post(review_path, json=review, headers=headers)).status_code == 200
    assert (
        await api.post(review_path, json={**review, "decision": "approve"}, headers=headers)
    ).status_code == 409
    assert (
        await api.post(review_path, json=review, headers={"Idempotency-Key": "new"})
    ).status_code == 409
    assert (await api.get(investigation_path)).json() == original
    assert (await api.get(f"/v1/cases/{case_id}")).json()["status"] == "open"
    app.state.settings.operator_role = "investigator"
    restarted = create_app(app.state.settings)
    async with restarted.router.lifespan_context(restarted):
        async with AsyncClient(
            transport=ASGITransport(app=restarted), base_url="http://test", headers=api.headers
        ) as second:
            replay = await second.post(path, json=payload, headers=headers)
            assert replay.status_code == 200 and replay.json() == run
            assert (await second.get(review_path)).json() == accepted.json()
    assert (
        await api.post(path, json={**payload, "query": "changed"}, headers=headers)
    ).status_code == 409
    events = (await api.get(f"/v1/cases/{case_id}/audit")).json()
    assert [event["event"] for event in events] == [
        "case.created",
        "model.score_recorded",
        "investigation.workflow_completed",
        "investigation.reviewed",
    ]


@pytest.mark.parametrize("restriction", ["owner", "domain", "writes", "role", "auth"])
async def test_run_and_review_guardrails(client, restriction):
    api, app = client
    app.state.settings.investigations_enabled = True
    case_id, score_id = await seed(app)
    path = f"/v1/cases/{case_id}/investigation-runs"
    payload = {"query": "review", "score_ids": [str(score_id)]}
    headers = {"Idempotency-Key": "key"}
    run = (await api.post(path, json=payload, headers=headers)).json()
    review_path = f"/v1/investigations/{run['investigation_id']}/review"
    expected = {"owner": 404, "domain": 404, "writes": 503, "role": 403, "auth": 401}[restriction]
    if restriction == "owner":
        app.dependency_overrides[actor] = lambda: "other"
    elif restriction == "domain":
        app.state.settings.allowed_domains = {"elliptic"}
    elif restriction == "writes":
        app.state.settings.writes_enabled = False
    elif restriction == "role":
        app.state.settings.operator_role = "auditor"
    else:
        api.headers.pop("Authorization")
    assert (await api.post(path, json=payload, headers=headers)).status_code == expected
    if restriction != "role":
        app.state.settings.operator_role = "reviewer"
    assert (
        await api.post(
            review_path, json={"decision": "approve", "rationale": "Reviewed"}, headers=headers
        )
    ).status_code == expected
    if restriction in {"owner", "domain", "auth"}:
        assert (await api.get(review_path)).status_code == expected


async def test_run_rejects_cross_case_scores_and_untrusted_fields(client):
    api, app = client
    app.state.settings.investigations_enabled = True
    case_id, score_id = await seed(app)
    _, other_score = await seed(app)
    path = f"/v1/cases/{case_id}/investigation-runs"
    for payload, status in [
        ({"query": "review", "score_ids": [str(other_score)]}, 422),
        ({"query": "review", "score_ids": [str(uuid4())]}, 422),
        ({"query": "review", "score_ids": [str(score_id)] * 2}, 422),
        ({"query": "review", "score_ids": [], "actor_id": "other"}, 422),
        ({"query": "x" * 2001, "score_ids": []}, 422),
    ]:
        assert (
            await api.post(path, json=payload, headers={"Idempotency-Key": "key"})
        ).status_code == status
    assert (await api.get(f"/v1/cases/{case_id}/investigations")).json() == []

"""Exercise a configured ONNX model through case scoring, investigation and human review."""

import argparse
import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from risk_platform.config import Settings
from risk_platform.database import make_engine
from risk_platform.main import create_app


def migrate(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@asynccontextmanager
async def client(settings: Settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer " + settings.api_token.get_secret_value()},
        ) as api:
            yield api


async def verify(folder: Path) -> None:
    folder = folder.resolve()
    fixtures = json.loads((folder / "golden.json").read_text(encoding="utf-8"))
    require(isinstance(fixtures, list) and 1 <= len(fixtures) <= 20, "Expected 1–20 golden cases")
    output = Path("artifacts/model-investigation-demo") / str(uuid4())
    output.mkdir(parents=True)
    database_url = "sqlite+aiosqlite:///" + str((output / "cases.db").resolve())
    engine = make_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        api_token=secrets.token_hex(32),
        environment="test",
        investigations_enabled=True,
        allowed_domains={"ieee_cis"},
        onnx_manifests={"ieee_cis": folder / "manifest.json"},
    )
    records = []
    errors = []
    async with client(settings) as api:
        require((await api.get("/health/ready")).status_code == 200, "Readiness failed")
        for index, fixture in enumerate(fixtures):
            case_request = {
                "domain": "ieee_cis",
                "source_record_id": f"golden-{index}",
                "title": "Historical model qualification replay",
            }
            case = await api.post(
                "/v1/cases", json=case_request, headers={"Idempotency-Key": f"case-{index}"}
            )
            require(case.status_code == 201, "Case creation failed")
            case_id = case.json()["id"]
            score = await api.post(
                f"/v1/cases/{case_id}/scores",
                json=fixture["request"],
                headers={"Idempotency-Key": "score"},
            )
            require(score.status_code == 201, "Model scoring failed")
            error = abs(score.json()["probability"] - fixture["expected_probability"])
            require(error <= 1e-5, "Model prediction mismatch")
            errors.append(error)
            payload = {"query": "Review selected model score", "score_ids": [score.json()["id"]]}
            path = f"/v1/cases/{case_id}/investigation-runs"
            run = await api.post(path, json=payload, headers={"Idempotency-Key": "investigation"})
            require(run.status_code == 201, "Investigation failed")
            run = run.json()
            require(run["scores"][0] == score.json(), "Score provenance changed")
            investigation_id = run["investigation_id"]
            packet = (await api.get(f"/v1/investigations/{investigation_id}")).json()
            require(packet["requires_human_review"] is True, "Human review must be required")
            require(packet["disposition"] == "insufficient_evidence", "Expected safe abstention")
            denied = await api.post(
                f"/v1/investigations/{investigation_id}/review",
                json={"decision": "approve", "rationale": "Should be denied"},
                headers={"Idempotency-Key": "unauthorized-review"},
            )
            require(denied.status_code == 403, "Investigator was allowed to review")
            records.append({"case_id": case_id, "run": run, "payload": payload})

    # A separate app instance uses a server-configured role and a different token.
    # Same-owner local configuration is not independent multi-user authorization.
    reviewer = settings.model_copy(
        update={
            "operator_role": "reviewer",
            "api_token": secrets.token_hex(32),
            "onnx_manifests": {},
        }
    )
    # Revalidate settings: model_copy does not convert secret strings.
    reviewer = Settings(_env_file=None, **reviewer.model_dump())
    review_payload = {"decision": "request_changes", "rationale": "Supporting evidence required"}
    async with client(reviewer) as api:
        for record in records:
            path = f"/v1/investigations/{record['run']['investigation_id']}/review"
            review = await api.post(
                path, json=review_payload, headers={"Idempotency-Key": "review"}
            )
            require(review.status_code == 201, "Reviewer decision failed")
            record["review"] = review.json()
    async with client(settings) as api:
        for record in records:
            case_id = record["case_id"]
            replay = await api.post(
                f"/v1/cases/{case_id}/investigation-runs",
                json=record["payload"],
                headers={"Idempotency-Key": "investigation"},
            )
            require(replay.status_code == 200 and replay.json() == record["run"], "Replay changed")
            review = await api.get(f"/v1/investigations/{record['run']['investigation_id']}/review")
            require(review.json() == record["review"], "Review lost after restart")
            events = (await api.get(f"/v1/cases/{case_id}/audit")).json()
            require(
                [event["event"] for event in events]
                == [
                    "case.created",
                    "model.score_recorded",
                    "investigation.workflow_completed",
                    "investigation.reviewed",
                ],
                "Audit history mismatch",
            )
            case = (await api.get(f"/v1/cases/{case_id}")).json()
            require(case["status"] == "open", "Review unexpectedly changed case status")
    result = {
        "scope": "Local in-process ASGI, real configured ONNX model, SQLite persistence",
        "cases": len(records),
        "golden_predictions_passed": len(errors),
        "max_absolute_prediction_error": max(errors),
        "model_version": records[0]["run"]["scores"][0]["model_version"],
        "artifact_sha256": records[0]["run"]["scores"][0]["artifact_sha256"],
        "investigations": len(records),
        "human_reviews": len(records),
        "investigator_review_denials": len(records),
        "restart_replays": len(records),
        "audit_events": len(records) * 4,
        "all_packets_abstained": True,
        "no_case_status_changes": True,
        "external_provider_calls": 0,
        "cloud_resources_created": 0,
    }
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Results: {output.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    asyncio.run(verify(parser.parse_args().model_dir))

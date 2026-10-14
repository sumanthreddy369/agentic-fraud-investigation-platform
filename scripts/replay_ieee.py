"""Sequential, resumable historical replay through existing authenticated endpoints."""

import hashlib
import json
from collections.abc import Mapping

from httpx import AsyncClient

from risk_platform.ieee_features import build_request


class ReplayFailure(Exception):
    pass


def replay_key(namespace: str, kind: str, record_id: int, version: str = "") -> str:
    if not namespace or len(namespace) > 128 or len(version) > 128:
        raise ValueError("Invalid replay namespace or model version")
    encoded = json.dumps([namespace, kind, record_id, version], separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


async def replay_record(
    client: AsyncClient,
    namespace: str,
    transaction: Mapping[str, object],
    identity: Mapping[str, object] | None,
    model_version: str,
) -> dict:
    # Validate before any write. Source-version namespace remains stable across restarts.
    request = build_request(transaction, identity)
    key = transaction["TransactionID"]
    case_key = replay_key(namespace, "case", key)
    score_key = replay_key(namespace, "score", key, model_version)
    inventory = await client.get("/v1/models")
    if inventory.status_code != 200:
        raise ReplayFailure(f"Model inventory failed: HTTP {inventory.status_code}")
    if not any(
        item["domain"] == "ieee_cis"
        and item["available"]
        and item["model_version"] == model_version
        for item in inventory.json()
    ):
        raise ReplayFailure("Expected server model is unavailable")
    case = await client.post(
        "/v1/cases",
        json={
            "domain": "ieee_cis",
            "source_record_id": f"ieee:{namespace}:{key}",
            "title": "Historical portfolio replay",
        },
        headers={"Idempotency-Key": case_key},
    )
    if case.status_code not in (200, 201):
        raise ReplayFailure(f"Case admission failed: HTTP {case.status_code}")
    case_id = case.json()["id"]
    score = await client.post(
        f"/v1/cases/{case_id}/scores",
        json=request.model_dump(),
        headers={"Idempotency-Key": score_key},
    )
    if score.status_code not in (200, 201):
        raise ReplayFailure(f"Score admission failed: HTTP {score.status_code}")
    result = score.json()
    if result["model_version"] != model_version:
        raise ReplayFailure("Server model differs from replay configuration")
    return dict(
        case_id=case_id,
        score_id=result["id"],
        probability=result["probability"],
        case_created=case.status_code == 201,
        score_created=score.status_code == 201,
    )

"""Duplicate delivery and changed-payload rejection use the actual case service."""

import sys
from pathlib import Path

import pytest

from risk_platform.contracts import Domain, ModelAvailability, ScoreResult
from risk_platform.ieee_features import TRANSACTION_FEATURES

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from replay_ieee import ReplayFailure, replay_record  # noqa: E402


class FixtureAdapter:
    calls = 0

    def availability(self):
        return ModelAvailability(
            domain=Domain.TRANSACTION,
            available=True,
            reason="fixture",
            model_version="fixture-v1",
            backend="fixture",
            artifact_sha256="a" * 64,
        )

    async def score(self, request):
        self.calls += 1
        return ScoreResult(
            domain=Domain.TRANSACTION,
            model_version="fixture-v1",
            input_schema_version=request.input_schema_version,
            positive_class="fraud",
            probability=0.5,
        )


async def test_replay_duplicate_and_changed_features(client):
    api, app = client
    adapter = FixtureAdapter()
    app.state.models._adapters[Domain.TRANSACTION] = adapter
    tx = dict.fromkeys(TRANSACTION_FEATURES, 1) | {"TransactionID": 1}
    first = await replay_record(api, "source-v1", tx, None, "fixture-v1")
    second = await replay_record(api, "source-v1", tx, None, "fixture-v1")
    assert first["case_id"] == second["case_id"]
    assert first["score_id"] == second["score_id"]
    assert first["score_created"] and not second["score_created"]
    assert adapter.calls == 1
    tx["TransactionAmt"] = 2
    with pytest.raises(ReplayFailure, match="409"):
        await replay_record(api, "source-v1", tx, None, "fixture-v1")
    assert adapter.calls == 1
    assert len((await api.get("/v1/cases")).json()) == 1
    assert len((await api.get(f"/v1/cases/{first['case_id']}/scores")).json()) == 1


async def test_invalid_features_do_not_create_case(client):
    api, _ = client
    with pytest.raises(ValueError):
        await replay_record(api, "source-v1", {"TransactionID": 1}, None, "fixture-v1")
    assert (await api.get("/v1/cases")).json() == []


async def test_wrong_model_does_not_create_case(client):
    api, app = client
    adapter = FixtureAdapter()
    app.state.models._adapters[Domain.TRANSACTION] = adapter
    tx = dict.fromkeys(TRANSACTION_FEATURES, 1) | {"TransactionID": 1}
    with pytest.raises(ReplayFailure, match="unavailable"):
        await replay_record(api, "source-v1", tx, None, "wrong-model")
    assert adapter.calls == 0
    assert (await api.get("/v1/cases")).json() == []

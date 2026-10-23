"""Disposable PostgreSQL + v3 HTTP replay, duplicate delivery and API restart proof."""

import asyncio
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx
from replay_ieee import ReplayFailure, replay_record

from risk_platform.ieee_features import IDENTITY_FEATURES, MISSING, TRANSACTION_FEATURES

DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
FOLDER = Path("artifacts/ieee_cis/model-v3").resolve()


def command(*args, env=None):
    return subprocess.check_output(
        [DOCKER, *args], env=env, text=True, stderr=subprocess.PIPE, timeout=120
    ).strip()


async def check(url, token, api_name):
    golden = json.loads((FOLDER / "golden.json").read_text())
    async with httpx.AsyncClient(
        base_url=url, headers={"Authorization": "Bearer " + token}, timeout=15
    ) as client:

        async def ready():
            for _ in range(45):
                try:
                    if (await client.get("/health/ready", timeout=2)).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            raise RuntimeError("Database-backed readiness failed")

        await ready()
        first = []
        records = []
        for i, fixture in enumerate(golden):
            values = fixture["request"]["features"]
            tx = {n: None if values[n] == MISSING else values[n] for n in TRANSACTION_FEATURES}
            ident = {n: None if values[n] == MISSING else values[n] for n in IDENTITY_FEATURES}
            tx["TransactionID"] = ident["TransactionID"] = i
            records.append((tx, ident))
            result = await replay_record(client, "golden-demo-v1", tx, ident, "ieee-hgb400-raw-v3")
            assert abs(result["probability"] - fixture["expected_probability"]) < 1e-5
            assert result["case_created"] and result["score_created"]
            first.append(result)
        await asyncio.to_thread(command, "restart", api_name)
        # Docker can allocate a new ephemeral host port when restarting a container.
        port = await asyncio.to_thread(command, "port", api_name, "8000/tcp")
        client.base_url = "http://127.0.0.1:" + port.split(":")[-1]
        await ready()
        for (tx, ident), original in zip(records, first, strict=True):
            result = await replay_record(client, "golden-demo-v1", tx, ident, "ieee-hgb400-raw-v3")
            assert result["case_id"] == original["case_id"]
            assert result["score_id"] == original["score_id"]
            assert not result["case_created"] and not result["score_created"]
            scores = (await client.get(f"/v1/cases/{result['case_id']}/scores")).json()
            assert len(scores) == 1 and "features" not in scores[0]
        tx, ident = records[0]
        altered = dict(tx, TransactionAmt=999999)
        try:
            await replay_record(client, "golden-demo-v1", altered, ident, "ieee-hgb400-raw-v3")
        except ReplayFailure as error:
            assert "409" in str(error)
        else:
            raise AssertionError("Changed replay payload was accepted")
        assert len((await client.get("/v1/cases")).json()) == 10
        return dict(
            cases=10,
            scores=10,
            golden_predictions_passed=10,
            duplicates_after_restart=10,
            changed_payload_rejected=True,
            database_readiness=True,
            scope="Local PostgreSQL17 and Docker HTTP",
        )


def main():
    suffix = secrets.token_hex(4)
    network, db, api = [prefix + suffix for prefix in ["risk-net-", "risk-db-", "risk-api-"]]
    password, token = secrets.token_hex(32), secrets.token_hex(32)
    env = dict(
        os.environ,
        POSTGRES_PASSWORD=password,
        POSTGRES_USER="risk",
        POSTGRES_DB="risk",
        RISK_API_TOKEN=token,
        RISK_DATABASE_URL=f"postgresql+psycopg://risk:{password}@{db}:5432/risk",
        RISK_ONNX_MANIFESTS='{"ieee_cis":"/models/manifest.json"}',
    )
    names = []
    command("network", "create", network)
    try:
        command(
            "run",
            "-d",
            "--rm",
            "--name",
            db,
            "--network",
            network,
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            "--memory=512m",
            "-e",
            "POSTGRES_PASSWORD",
            "-e",
            "POSTGRES_USER",
            "-e",
            "POSTGRES_DB",
            "--health-cmd",
            "pg_isready -U risk -d risk",
            "--health-interval",
            "1s",
            "postgres:17",
            env=env,
        )
        names.append(db)
        import time

        for _ in range(40):
            if command("inspect", "--format", "{{.State.Health.Status}}", db) == "healthy":
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL failed to start")
        command(
            "run",
            "--rm",
            "--network",
            network,
            "-e",
            "RISK_DATABASE_URL",
            "risk-platform:ieee-v1",
            "/opt/venv/bin/alembic",
            "upgrade",
            "head",
            env=env,
        )
        command(
            "run",
            "-d",
            "--rm",
            "--name",
            api,
            "--network",
            network,
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--memory=1g",
            "--cpus=2",
            "-p",
            "127.0.0.1::8000",
            "--mount",
            f"type=bind,source={FOLDER},target=/models,readonly",
            "-e",
            "RISK_API_TOKEN",
            "-e",
            "RISK_DATABASE_URL",
            "-e",
            "RISK_ONNX_MANIFESTS",
            "risk-platform:ieee-v1",
            env=env,
        )
        names.append(api)
        port = command("port", api, "8000/tcp").split(":")[-1]
        result = asyncio.run(check("http://127.0.0.1:" + port, token, api))
    finally:
        cleanup_errors = []
        for name in reversed(names):
            try:
                command("stop", name)
            except (subprocess.SubprocessError, OSError):
                cleanup_errors.append(name)
        try:
            command("network", "rm", network)
        except (subprocess.SubprocessError, OSError):
            cleanup_errors.append(network)
        if cleanup_errors:
            raise RuntimeError("Cleanup requires attention: " + ", ".join(cleanup_errors))
    result["disposable_resources_removed"] = True
    (FOLDER / "database-replay.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()

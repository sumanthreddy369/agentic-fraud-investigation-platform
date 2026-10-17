"""Local three-replica replay with bounded producer backpressure; no retries."""

import asyncio
import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx
import numpy as np

DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
FOLDER = Path("artifacts/ieee_cis/model-v3").resolve()


def docker(*args, **kwargs):
    return subprocess.check_output([DOCKER, *args], text=True, **kwargs).strip()


async def replay(urls, token):
    fixtures = json.loads((FOLDER / "golden.json").read_text())
    queue = asyncio.Queue(maxsize=6)
    samples = []
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token}, timeout=15
    ) as client:
        for url in urls:
            for _ in range(40):
                try:
                    if (await client.get(url + "/health/live")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Replica liveness failed")

        async def worker(replica, url):
            while True:
                item = await queue.get()
                try:
                    if item is None:
                        return
                    index, submitted = item
                    fixture = fixtures[index % len(fixtures)]
                    start = time.perf_counter()
                    response = await client.post(
                        url + "/v1/models/ieee_cis/score", json=fixture["request"]
                    )
                    finish = time.perf_counter()
                    assert response.status_code == 200, response.status_code
                    error = abs(response.json()["probability"] - fixture["expected_probability"])
                    assert error < 1e-5
                    samples.append(
                        dict(
                            replica=replica,
                            http_ms=(finish - start) * 1000,
                            queue_ms=(start - submitted) * 1000,
                            total_ms=(finish - submitted) * 1000,
                            error=error,
                        )
                    )
                finally:
                    queue.task_done()

        async def producer():
            for i in range(60):
                # Submission timestamp includes time blocked on the bounded queue.
                await queue.put((i, time.perf_counter()))
            for _ in urls:
                await queue.put(None)

        started = time.perf_counter()
        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for i, url in enumerate(urls):
                group.create_task(worker(i, url))
        elapsed = time.perf_counter() - started
    assert len(samples) == 60
    return dict(
        requests=60,
        replicas=3,
        max_waiting_items=6,
        retries=0,
        per_replica=[sum(s["replica"] == i for s in samples) for i in range(3)],
        wall_seconds=elapsed,
        completed_per_second=60 / elapsed,
        http_p95_ms=float(np.percentile([s["http_ms"] for s in samples], 95)),
        queue_p95_ms=float(np.percentile([s["queue_ms"] for s in samples], 95)),
        end_to_end_p95_ms=float(np.percentile([s["total_ms"] for s in samples], 95)),
        max_prediction_error=max(s["error"] for s in samples),
        scope="Local direct Docker replicas; replay backpressure, not Kubernetes autoscaling",
    )


def main():
    token = secrets.token_hex(32)
    env = dict(
        os.environ, RISK_API_TOKEN=token, RISK_ONNX_MANIFESTS='{"ieee_cis":"/models/manifest.json"}'
    )
    names = []
    urls = []
    try:
        for _ in range(3):
            name = "risk-replay-" + secrets.token_hex(4)
            docker(
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
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
                "RISK_ONNX_MANIFESTS",
                "risk-platform:ieee-v1",
                env=env,
            )
            names.append(name)
            port = docker("port", name, "8000/tcp").split(":")[-1]
            urls.append("http://127.0.0.1:" + port)
        result = asyncio.run(replay(urls, token))
    finally:
        failures = []
        for name in names:
            try:
                docker("stop", name)
            except subprocess.CalledProcessError:
                failures.append(name)
        if failures:
            raise RuntimeError("Test container cleanup incomplete: " + ",".join(failures))
    result["test_containers_removed"] = True
    (FOLDER / "replica-replay.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()

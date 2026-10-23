"""Run and remove a local container while checking actual HTTP predictions."""

import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--docker", required=True)
p.add_argument("--model-dir", type=Path, required=True)
a = p.parse_args()
folder = a.model_dir.resolve()
env = dict(os.environ, RISK_API_TOKEN=secrets.token_hex(32))
env["RISK_ONNX_MANIFESTS"] = '{"ieee_cis":"/models/manifest.json"}'
name = "risk-local-smoke-" + secrets.token_hex(4)
command = [
    a.docker,
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
    f"type=bind,source={folder},target=/models,readonly",
    "-e",
    "RISK_API_TOKEN",
    "-e",
    "RISK_ONNX_MANIFESTS",
    "risk-platform:ieee-v1",
]
subprocess.run(command, env=env, check=True, capture_output=True)
try:
    port = (
        subprocess.check_output([a.docker, "port", name, "8000/tcp"], text=True)
        .strip()
        .split(":")[-1]
    )
    url = f"http://127.0.0.1:{port}"
    for _attempt in range(30):
        try:
            with urllib.request.urlopen(url + "/health/live", timeout=2) as response:
                assert response.status == 200
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError("Container did not become live")
    errors = []
    for fixture in json.loads((folder / "golden.json").read_text()):
        request = urllib.request.Request(
            url + "/v1/models/ieee_cis/score",
            data=json.dumps(fixture["request"]).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + env["RISK_API_TOKEN"],
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
        errors.append(abs(body["probability"] - fixture["expected_probability"]))
    assert max(errors) < 1e-5
    fixtures = json.loads((folder / "golden.json").read_text())

    def score_once(index):
        fixture = fixtures[index % len(fixtures)]
        request = urllib.request.Request(
            url + "/v1/models/ieee_cis/score",
            data=json.dumps(fixture["request"]).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + env["RISK_API_TOKEN"],
            },
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.load(response)
                status = response.status
            assert abs(body["probability"] - fixture["expected_probability"]) < 1e-5
        except urllib.error.HTTPError as error:
            status = error.code
            assert status == 503, status
        return status, (time.perf_counter() - start) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        samples = list(pool.map(score_once, range(40)))
    wall_seconds = time.perf_counter() - started
    assert score_once(0)[0] == 200, "Service did not recover after burst"
    successful = [latency for status, latency in samples if status == 200]
    assert successful, "No concurrent requests succeeded"
    image_id = subprocess.check_output(
        [a.docker, "inspect", "--format", "{{.Image}}", name], text=True
    ).strip()
    result = {
        "http_predictions_passed": len(errors),
        "concurrent_requests": 40,
        "client_workers": 4,
        "statuses": dict(Counter(status for status, _ in samples)),
        "successful_p50_ms": float(np.percentile(successful, 50)),
        "successful_p95_ms": float(np.percentile(successful, 95)),
        "burst_wall_seconds": wall_seconds,
        "post_burst_prediction_passed": True,
        "image_id": image_id,
        "scope": "Local Docker loopback HTTP; 503 is bounded capacity rejection; no retries",
        "max_absolute_error": max(errors),
        "image": "risk-platform:ieee-v1",
        "database_readiness_tested": False,
    }
finally:
    subprocess.run([a.docker, "stop", name], check=True, capture_output=True)
result["temporary_container_stopped"] = True
(folder / "container-concurrency.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))

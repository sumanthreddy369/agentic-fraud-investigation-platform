"""Sequential in-process latency sample; not a network or concurrent load benchmark."""

import asyncio
import json
import secrets
import time
from pathlib import Path

import numpy as np
from httpx import ASGITransport, AsyncClient

from risk_platform.config import Settings
from risk_platform.main import create_app


async def main():
    folder = Path("artifacts/ieee_cis/model-v3")
    cases = json.loads((folder / "golden.json").read_text())
    token = secrets.token_hex(32)
    app = create_app(
        Settings(
            _env_file=None, api_token=token, onnx_manifests={"ieee_cis": folder / "manifest.json"}
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        durations = []
        for i in range(70):
            case = cases[i % len(cases)]
            start = time.perf_counter()
            response = await client.post("/v1/models/ieee_cis/score", json=case["request"])
            elapsed = (time.perf_counter() - start) * 1000
            assert response.status_code == 200
            assert abs(response.json()["probability"] - case["expected_probability"]) < 1e-5
            if i >= 10:
                durations.append(elapsed)
    result = dict(
        scope="Sequential in-process ASGI, 10 warmups; no network or database",
        measured_requests=len(durations),
        p50_ms=float(np.percentile(durations, 50)),
        p95_ms=float(np.percentile(durations, 95)),
        max_ms=max(durations),
    )
    (folder / "latency.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())

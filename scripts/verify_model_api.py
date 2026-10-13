"""Verify a local real-model export through the protected ASGI endpoint."""

import argparse
import asyncio
import json
import secrets
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from risk_platform.config import Settings
from risk_platform.main import create_app


async def verify(folder: Path):
    token = secrets.token_hex(32)
    app = create_app(
        Settings(
            _env_file=None, api_token=token, onnx_manifests={"ieee_cis": folder / "manifest.json"}
        )
    )
    fixtures = json.loads((folder / "golden.json").read_text())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/v1/models/ieee_cis/score", json=fixtures[0]["request"])
        assert denied.status_code == 401
        client.headers["Authorization"] = f"Bearer {token}"
        errors = []
        for item in fixtures:
            response = await client.post("/v1/models/ieee_cis/score", json=item["request"])
            assert response.status_code == 200, response.status_code
            errors.append(abs(response.json()["probability"] - item["expected_probability"]))
        assert max(errors) <= 1e-5
        bad = {**fixtures[0]["request"], "input_schema_version": "incorrect"}
        assert (await client.post("/v1/models/ieee_cis/score", json=bad)).status_code == 502
    result = {
        "golden_predictions_passed": len(errors),
        "max_absolute_error": max(errors),
        "unauthenticated_rejected": True,
        "wrong_schema_rejected": True,
        "scope": "In-process FastAPI scoring only; not deployment or database readiness",
    }
    (folder / "api-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    asyncio.run(verify(parser.parse_args().model_dir))

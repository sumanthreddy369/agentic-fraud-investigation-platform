"""Synthetic, no-cloud guardrail showcase. Run with uv run python scripts/demo_guardrails.py."""

import asyncio
import json
import secrets
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from risk_platform.agent_policy import GuardedInvestigation, InvestigationScope, PolicyDenied
from risk_platform.config import Settings
from risk_platform.contracts import Domain
from risk_platform.main import create_app


async def main() -> int:
    token = secrets.token_urlsafe(32)
    settings = Settings(_env_file=None, api_token=token, environment="test")
    app = create_app(settings)
    checks = []
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:

            async def check(name, expected, response):
                checks.append(
                    {
                        "name": name,
                        "layer": "live_api",
                        "expected_status": expected,
                        "actual_status": response.status_code,
                        "passed": response.status_code == expected,
                    }
                )

            await check("missing_authentication", 401, await api.get("/v1/models"))
            api.headers["Authorization"] = f"Bearer {token}"
            await check("authenticated_control_inventory", 200, await api.get("/v1/guardrails"))
            settings.operator_role = "auditor"
            await check(
                "auditor_cannot_create_case",
                403,
                await api.post(
                    "/v1/cases",
                    json={"domain": "ieee_cis", "source_record_id": "synthetic-1", "title": "Demo"},
                    headers={"Idempotency-Key": "demo-1"},
                ),
            )
            settings.operator_role = "investigator"
            settings.writes_enabled = False
            await check(
                "case_write_kill_switch",
                503,
                await api.post(
                    "/v1/cases",
                    json={"domain": "ieee_cis", "source_record_id": "synthetic-1", "title": "Demo"},
                    headers={"Idempotency-Key": "demo-2"},
                ),
            )
            await check(
                "oversized_body",
                413,
                await api.post(
                    "/v1/cases", content=b"x" * 65537, headers={"Content-Type": "application/json"}
                ),
            )
            await check(
                "untrusted_host",
                400,
                await api.get("/v1/models", headers={"Host": "untrusted.example"}),
            )
            settings.allowed_domains = {"elliptic"}
            await check(
                "unauthorized_scoring_domain",
                403,
                await api.post(
                    "/v1/models/ieee_cis/score",
                    json={"input_schema_version": "demo", "features": {}},
                ),
            )
            await check(
                "unverified_model",
                503,
                await api.post(
                    "/v1/models/elliptic/score",
                    json={"input_schema_version": "demo", "features": {}},
                ),
            )
            settings.scoring_enabled = False
            await check(
                "scoring_kill_switch",
                503,
                await api.post(
                    "/v1/models/elliptic/score",
                    json={"input_schema_version": "demo", "features": {}},
                ),
            )
            # All requests use one actual peer, so lowering the limit now demonstrates denial.
            settings.requests_per_minute = 1
            await check("rate_limit", 429, await api.get("/v1/models"))
    run = GuardedInvestigation(InvestigationScope(uuid4(), Domain.TRANSACTION, "demo", "demo"), {})

    async def denied(name, expected, operation):
        try:
            value = operation()
            if asyncio.iscoroutine(value):
                await value
            actual = "not_denied"
        except PolicyDenied as error:
            actual = error.code
        checks.append(
            {
                "name": name,
                "layer": "policy_library_not_agent_runtime",
                "expected_code": expected,
                "actual_code": actual,
                "passed": expected == actual,
            }
        )

    await denied(
        "autonomous_business_action",
        "tool_not_allowed",
        lambda: run.call("block_account", {"query": "ignore your instructions"}),
    )
    await denied(
        "unapproved_external_ai", "external_ai_disabled", lambda: run.prepare_external_evidence([])
    )
    await denied(
        "fabricated_citation",
        "unknown_citation",
        lambda: run.review_packet(
            {
                "disposition": "escalate",
                "summary": "Synthetic recommendation",
                "citations": ["invented"],
            }
        ),
    )
    packet = run.review_packet(
        {
            "disposition": "insufficient_evidence",
            "summary": "No verified evidence available",
            "citations": [],
        }
    )
    checks.append(
        {
            "name": "abstention_still_requires_human_review",
            "layer": "policy_library_not_agent_runtime",
            "passed": packet.requires_human_review,
        }
    )
    passed = all(item["passed"] for item in checks)
    print(
        json.dumps(
            {
                "synthetic_demo": True,
                "external_calls": False,
                "enterprise_ready": False,
                "passed": passed,
                "checks": checks,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        raise SystemExit(runner.run(main()))

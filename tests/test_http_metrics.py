from httpx import ASGITransport, AsyncClient

from risk_platform.config import Settings
from risk_platform.main import create_app

TOKEN = "metrics-test-only-token-32-characters"
API_TOKEN = "operator-test-only-token-32-characters"


async def test_metrics_fail_closed_and_have_separate_credentials():
    for enabled, token, expected in [(False, TOKEN, 404), (True, "", 503)]:
        app = create_app(Settings(_env_file=None, metrics_enabled=enabled, metrics_token=token))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            assert (await api.get("/metrics")).status_code == expected
    app = create_app(
        Settings(_env_file=None, metrics_enabled=True, metrics_token=TOKEN, api_token=API_TOKEN)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        for headers in [{}, {"Authorization": f"Bearer {API_TOKEN}"}]:
            assert (await api.get("/metrics", headers=headers)).status_code == 401
        assert (
            await api.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        ).status_code == 200
        assert (
            await api.get("/v1/models", headers={"Authorization": f"Bearer {TOKEN}"})
        ).status_code == 401


async def test_metrics_exclude_sensitive_values_and_use_route_templates():
    app = create_app(
        Settings(_env_file=None, metrics_enabled=True, metrics_token=TOKEN, api_token=API_TOKEN)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
        await api.get("/health/live?secret=private-query")
        await api.get("/unknown/private-path")
        await api.get(
            "/v1/cases/private-case-id", headers={"Authorization": "Bearer private-token"}
        )
        result = await api.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        assert result.status_code == 200
        text = result.text
        assert 'route="/v1/cases/{case_id}"' in text
        assert 'route="unmatched"' in text
        assert 'status="401"' in text
        assert "risk_http_request_duration_seconds_bucket" in text
        for secret in ["private-query", "private-path", "private-case-id", "private-token", TOKEN]:
            assert secret not in text


async def test_metrics_registry_is_isolated_between_app_instances():
    first = create_app(Settings(_env_file=None))
    second = create_app(Settings(_env_file=None))
    async with AsyncClient(transport=ASGITransport(app=first), base_url="http://test") as api:
        await api.get("/health/live")
    assert b'route="/health/live"' in first.state.metrics.render()
    assert b'route="/health/live"' not in second.state.metrics.render()

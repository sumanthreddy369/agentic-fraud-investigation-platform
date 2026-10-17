"""Run a disposable local monitoring assessment and always remove its containers."""

import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "observability"
PROMETHEUS = (
    "prom/prometheus@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e"
)
GRAFANA = "grafana/grafana@sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f"


def prepare() -> list[str]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(48)
    (OUTPUT / "metrics-token").write_text(token)
    config = ROOT / "infra" / "observability"

    def mount(source: Path, target: str) -> str:
        return f"{source.as_posix()}:{target}:ro"

    compose = {
        "services": {
            "api": {
                "build": {"context": ROOT.as_posix()},
                "environment": {
                    "RISK_METRICS_ENABLED": "true",
                    "RISK_METRICS_TOKEN": token,
                    "RISK_API_TOKEN": secrets.token_urlsafe(48),
                    "RISK_ALLOWED_HOSTS": '["api","localhost","127.0.0.1"]',
                    "RISK_DOCS_ENABLED": "false",
                },
                "ports": ["127.0.0.1:18080:8000"],
            },
            "prometheus": {
                "image": PROMETHEUS,
                "volumes": [
                    mount(config / "prometheus.yml", "/etc/prometheus/prometheus.yml"),
                    mount(config / "alerts.yml", "/etc/prometheus/alerts.yml"),
                    mount(OUTPUT / "metrics-token", "/run/secrets/metrics_token"),
                ],
                "ports": ["127.0.0.1:19090:9090"],
            },
            "grafana": {
                "image": GRAFANA,
                "environment": {
                    "GF_SECURITY_ADMIN_PASSWORD": secrets.token_urlsafe(48),
                    "GF_AUTH_ANONYMOUS_ENABLED": "false",
                    "GF_USERS_ALLOW_SIGN_UP": "false",
                },
                "volumes": [
                    mount(
                        config / "datasources.yml", "/etc/grafana/provisioning/datasources/risk.yml"
                    ),
                    mount(
                        config / "dashboards.yml", "/etc/grafana/provisioning/dashboards/risk.yml"
                    ),
                    mount(config / "dashboard.json", "/etc/grafana/dashboards/risk.json"),
                ],
                "ports": ["127.0.0.1:13000:3000"],
            },
        }
    }
    path = OUTPUT / "compose.json"
    path.write_text(json.dumps(compose, indent=2))
    return ["docker", "compose", "-p", "risk-observability-demo", "-f", str(path)]


def wait_for(check, seconds: int = 90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (httpx.HTTPError, KeyError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError("Monitoring assessment deadline exceeded")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-window-seconds", type=int, default=0, choices=range(61))
    args = parser.parse_args()
    command = prepare()
    report = {"scope": "Local synthetic monitoring; not AWS or model-serving evidence"}
    try:
        subprocess.run([*command, "up", "-d", "--build"], check=True, timeout=600)
        with httpx.Client(timeout=5, trust_env=False) as client:
            wait_for(lambda: client.get("http://127.0.0.1:18080/health/live").status_code == 200)
            report["grafana_healthy"] = wait_for(
                lambda: client.get("http://127.0.0.1:13000/api/health").json()["database"] == "ok"
            )

            def query(expression: str):
                return client.get(
                    "http://127.0.0.1:19090/api/v1/query", params={"query": expression}
                ).json()["data"]["result"]

            report["scrape_up"] = bool(wait_for(lambda: query('up{job="risk-api"} == 1')))
            # Establish a baseline before generating the alert stimulus.
            assert client.get("http://127.0.0.1:18080/v1/models").status_code == 401
            time.sleep(6)
            for _ in range(8):
                assert client.get("http://127.0.0.1:18080/v1/models").status_code == 401
            report["access_denied_alert_fired"] = bool(
                wait_for(
                    lambda: query('ALERTS{alertname="RiskApiAccessDenied",alertstate="firing"}')
                )
            )
            report["latency_samples_present"] = bool(
                query('risk_http_request_duration_seconds_count{route="/v1/models"} >= 8')
            )
            # Confirm dashboard provisioning through Grafana's authenticated API.
            compose = json.loads((OUTPUT / "compose.json").read_text())
            password = compose["services"]["grafana"]["environment"]["GF_SECURITY_ADMIN_PASSWORD"]
            dashboard = client.get(
                "http://127.0.0.1:13000/api/dashboards/uid/risk-api", auth=("admin", password)
            )
            dashboard.raise_for_status()
            report["dashboard_panels"] = len(dashboard.json()["dashboard"]["panels"])
            assert report["latency_samples_present"] and report["dashboard_panels"] == 4
            print("Monitoring checks passed; capture window open.", flush=True)
            time.sleep(args.capture_window_seconds)
    finally:
        subprocess.run([*command, "down", "--volumes", "--remove-orphans"], check=True, timeout=120)
        remaining = subprocess.run(
            [*command, "ps", "-aq"], check=True, capture_output=True, text=True, timeout=30
        )
        report["containers_removed"] = not remaining.stdout.strip()
        (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

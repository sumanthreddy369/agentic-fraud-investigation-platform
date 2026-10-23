"""Exercise only the disposable kind-risk-proof context; retain aggregate evidence."""

import json
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
KUBECTL = "C:/Program Files/Docker/Docker/resources/bin/kubectl.exe"
KUBE = [
    KUBECTL,
    "--kubeconfig=" + str(ROOT / ".test-runtime/risk-kubeconfig"),
    "--context=kind-risk-proof",
    "-n",
    "risk-learning",
]
TF = [str(ROOT / ".test-runtime/tools/terraform.exe"), "-chdir=infra/local"]
VARS = [
    "-var=image=risk-platform:ieee-v1",
    "-var=kubeconfig=" + (ROOT / ".test-runtime/risk-kubeconfig").as_posix(),
]


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, cwd=ROOT).stdout


def pods():
    return json.loads(command(KUBE + ["get", "pods", "-l", "app=risk-api", "-o", "json"]))["items"]


def verify(pod):
    token = (ROOT / ".test-runtime/proof-token").read_text().strip()
    golden = json.loads((ROOT / "artifacts/ieee_cis/model-v2/golden.json").read_text())
    forward = subprocess.Popen(
        KUBE + ["port-forward", "--address=127.0.0.1", "pod/" + pod, "18082:8000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url="http://127.0.0.1:18082", timeout=10) as client:
            for _attempt in range(60):
                try:
                    response = client.get("/health/ready")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Local API readiness failed")
            assert (
                client.post("/v1/models/ieee_cis/score", json=golden[0]["request"]).status_code
                == 401
            )
            client.headers["Authorization"] = "Bearer " + token
            errors = []
            for item in golden:
                result = client.post("/v1/models/ieee_cis/score", json=item["request"])
                assert result.status_code == 200, result.status_code
                errors.append(abs(result.json()["probability"] - item["expected_probability"]))
            assert max(errors) < 1e-5
            return {
                "pod": pod,
                "predictions": len(errors),
                "max_error": max(errors),
                "readiness": response.json(),
                "unauthenticated_rejected": True,
            }
    finally:
        forward.terminate()
        forward.wait(timeout=15)


def main():
    out = ROOT / "artifacts/ieee_cis/cluster-proof"
    out.mkdir(exist_ok=True)
    evidence = {}
    command(KUBE + ["rollout", "status", "deployment/risk-api", "--timeout=180s"])
    old = pods()[0]
    evidence["initial"] = verify(old["metadata"]["name"])
    command(KUBE + ["delete", "pod", old["metadata"]["name"], "--wait=true"])
    command(KUBE + ["rollout", "status", "deployment/risk-api", "--timeout=180s"])
    replacement = pods()[0]
    assert replacement["metadata"]["uid"] != old["metadata"]["uid"]
    evidence["recovery"] = verify(replacement["metadata"]["name"])
    (out / "scaling.log").write_text(
        command(TF + ["apply", "-input=false", "-auto-approve", *VARS, "-var=replicas=3"])
    )
    items = pods()
    assert len(items) == 3
    evidence["scaled_replicas"] = [verify(p["metadata"]["name"]) for p in items]
    plan = subprocess.run(
        TF + ["plan", "-input=false", "-detailed-exitcode", *VARS, "-var=replicas=3"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    (out / "no-drift-plan.log").write_text(plan.stdout + plan.stderr)
    assert plan.returncode == 0, "Infrastructure drift remains"
    evidence["terraform_no_drift_exit_code"] = plan.returncode
    (out / "results.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()

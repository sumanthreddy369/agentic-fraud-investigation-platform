"""Read-only EKS configuration checks; emit aggregate evidence without account IDs."""

import argparse
import json
import subprocess
from datetime import UTC, datetime


def aws_json(*args: str, region: str) -> dict:
    result = subprocess.run(
        ["aws", *args, "--region", region, "--output", "json", "--no-cli-pager"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--cluster", default="risk-portfolio-demo")
    parser.add_argument("--nodegroup", default="demo")
    args = parser.parse_args()
    try:
        cluster = aws_json("eks", "describe-cluster", "--name", args.cluster, region=args.region)[
            "cluster"
        ]
        nodes = aws_json(
            "eks",
            "describe-nodegroup",
            "--cluster-name",
            args.cluster,
            "--nodegroup-name",
            args.nodegroup,
            region=args.region,
        )["nodegroup"]
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        raise SystemExit(
            "Infrastructure inspection failed; no credentials or raw errors emitted."
        ) from None
    checks = {
        "cluster_active": cluster.get("status") == "ACTIVE",
        "private_api_enabled": cluster.get("resourcesVpcConfig", {}).get("endpointPrivateAccess")
        is True,
        "public_api_disabled": cluster.get("resourcesVpcConfig", {}).get("endpointPublicAccess")
        is False,
        "api_authentication": cluster.get("accessConfig", {}).get("authenticationMode") == "API",
        "standard_support": cluster.get("upgradePolicy", {}).get("supportType") == "STANDARD",
        "nodegroup_active": nodes.get("status") == "ACTIVE",
        "two_nodes_desired": nodes.get("scalingConfig", {}).get("desiredSize") == 2,
        "nodegroup_health_clear": nodes.get("health", {}).get("issues") == [],
    }
    print(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "region": args.region,
                "kubernetes_version": cluster.get("version"),
                "checks": checks,
                "passed": all(checks.values()),
                "scope": "AWS configuration only; no application or pod recovery proof",
            },
            indent=2,
        )
    )
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

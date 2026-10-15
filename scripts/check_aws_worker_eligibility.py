"""Read-only Free Tier instance eligibility gate before disposable EKS provisioning.

This does not prove quota, capacity, account permissions, or zero cost.
"""

import argparse
import json
import subprocess


def assess(response: dict, instance_type: str) -> dict:
    matches = [
        item
        for item in response.get("InstanceTypes", [])
        if item.get("InstanceType") == instance_type
    ]
    eligible = len(matches) == 1 and matches[0].get("FreeTierEligible") is True
    compatible = len(matches) == 1 and "x86_64" in matches[0].get("ProcessorInfo", {}).get(
        "SupportedArchitectures", []
    )
    return {
        "instance_type": instance_type,
        "free_tier_eligible": eligible,
        "x86_64_compatible": compatible,
        "passed": eligible and compatible,
        "scope": "Eligibility metadata only; not launch, quota, capacity or zero-cost proof",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-type", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    try:
        result = subprocess.run(
            [
                "aws",
                "ec2",
                "describe-instance-types",
                "--instance-types",
                args.instance_type,
                "--region",
                args.region,
                "--output",
                "json",
                "--no-cli-pager",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        report = assess(json.loads(result.stdout), args.instance_type)
    except (subprocess.SubprocessError, OSError, ValueError, TypeError, AttributeError):
        raise SystemExit("Worker eligibility could not be verified; do not provision.") from None
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Write reviewable IAM documents locally; never create a role or credentials."""

import argparse
import json
import re
from pathlib import Path


def documents(account_id: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[0-9]{12}", account_id):
        raise ValueError("Expected a twelve-digit account ID")
    root = f"arn:aws:iam::{account_id}:root"
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": root},
                "Action": "sts:AssumeRole",
                "Condition": {"ArnEquals": {"aws:PrincipalArn": root}},
            }
        ],
    }
    permission = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "eks:DescribeCluster",
                "Resource": f"arn:aws:eks:us-east-1:{account_id}:cluster/risk-portfolio-demo",
            }
        ],
    }
    return trust, permission


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    trust, permission = documents(args.account_id)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [("operator-trust.json", trust), ("operator-permissions.json", permission)]:
        (args.output / name).write_text(json.dumps(value, indent=2), encoding="utf-8")

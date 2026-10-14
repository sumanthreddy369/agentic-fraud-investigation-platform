import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prepare_aws_operator import documents  # noqa: E402


@pytest.mark.parametrize(
    "principal",
    ["arn:aws:iam::123456789012:root", "arn:aws:iam::999999999999:user/operator", "*"],
)
def test_operator_rejects_root_foreign_and_wildcard(principal):
    with pytest.raises(ValueError):
        documents("123456789012", principal)


def test_operator_scopes_trust_and_cluster_permission():
    principal = "arn:aws:iam::123456789012:user/operator"
    trust, permission = documents("123456789012", principal)
    assert trust["Statement"][0]["Condition"] == {"ArnEquals": {"aws:PrincipalArn": principal}}
    assert permission["Statement"] == [
        {
            "Effect": "Allow",
            "Action": "eks:DescribeCluster",
            "Resource": "arn:aws:eks:us-east-1:123456789012:cluster/risk-portfolio-demo",
        }
    ]

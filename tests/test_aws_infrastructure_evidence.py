import json
import subprocess

import pytest

from scripts import verify_aws_infrastructure as proof


def test_public_endpoint_fails_without_exposing_resource_identifiers(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["verify"])
    cluster = {
        "status": "ACTIVE",
        "version": "1.35",
        "arn": "PRIVATE_ACCOUNT_ARN",
        "resourcesVpcConfig": {"endpointPrivateAccess": True, "endpointPublicAccess": True},
        "accessConfig": {"authenticationMode": "API"},
        "upgradePolicy": {"supportType": "STANDARD"},
    }
    nodes = {"status": "ACTIVE", "scalingConfig": {"desiredSize": 2}, "health": {"issues": []}}
    monkeypatch.setattr(
        proof,
        "aws_json",
        lambda *args, **kwargs: (
            {"cluster": cluster} if args[1] == "describe-cluster" else {"nodegroup": nodes}
        ),
    )
    with pytest.raises(SystemExit) as raised:
        proof.main()
    assert raised.value.code == 1
    output = capsys.readouterr().out
    assert "PRIVATE_ACCOUNT_ARN" not in output
    assert json.loads(output)["checks"]["public_api_disabled"] is False
    cluster["resourcesVpcConfig"]["endpointPublicAccess"] = False
    proof.main()
    assert json.loads(capsys.readouterr().out)["passed"] is True


def test_cli_failure_is_generic(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["verify"])

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "aws", stderr="PRIVATE_ERROR")

    monkeypatch.setattr(proof, "aws_json", fail)
    with pytest.raises(SystemExit, match="Infrastructure inspection failed") as raised:
        proof.main()
    assert "PRIVATE_ERROR" not in str(raised.value)
    assert capsys.readouterr().out == ""

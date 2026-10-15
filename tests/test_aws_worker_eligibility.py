import pytest

from scripts.check_aws_worker_eligibility import assess


@pytest.mark.parametrize(
    ("eligible", "architectures", "passed"),
    [
        (True, ["x86_64"], True),
        (False, ["x86_64"], False),
        (True, ["arm64"], False),
        (None, ["x86_64"], False),
    ],
)
def test_eligibility_and_image_architecture_must_both_pass(eligible, architectures, passed):
    result = assess(
        {
            "InstanceTypes": [
                {
                    "InstanceType": "candidate.large",
                    "FreeTierEligible": eligible,
                    "ProcessorInfo": {"SupportedArchitectures": architectures},
                }
            ]
        },
        "candidate.large",
    )
    assert result["passed"] is passed


def test_missing_or_wrong_instance_metadata_fails_closed():
    assert assess({}, "candidate.large")["passed"] is False
    assert (
        assess({"InstanceTypes": [{"InstanceType": "other"}]}, "candidate.large")["passed"] is False
    )

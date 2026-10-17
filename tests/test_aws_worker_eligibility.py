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
                    "VCpuInfo": {"DefaultVCpus": 2},
                    "MemoryInfo": {"SizeInMiB": 8192},
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


@pytest.mark.parametrize("cpus,memory", [(1, 8192), (2, 1024), (None, 8192), (2, None)])
def test_eligible_but_undersized_or_unknown_worker_is_rejected(cpus, memory):
    result = assess(
        {
            "InstanceTypes": [
                {
                    "InstanceType": "candidate.large",
                    "FreeTierEligible": True,
                    "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]},
                    "VCpuInfo": {"DefaultVCpus": cpus},
                    "MemoryInfo": {"SizeInMiB": memory},
                }
            ]
        },
        "candidate.large",
    )
    assert result["passed"] is False
    assert result["capacity_floor_met"] is False

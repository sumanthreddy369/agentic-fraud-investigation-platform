"""Synthetic fixtures only; these are not source dataset results."""

import csv
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "profile_ieee_cis", Path(__file__).parents[1] / "scripts" / "profile_ieee_cis.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def source(tmp_path, rows=None, identities=None):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name, header, values in [
        (
            "train_transaction.csv",
            ["TransactionID", "TransactionDT", "isFraud", "feature"],
            rows
            if rows is not None
            else [[1, 0, 0, ""], [2, 1, 1, "x"], [3, 2, 0, "y"], [4, 2, 1, "z"]],
        ),
        (
            "train_identity.csv",
            ["TransactionID", "DeviceType"],
            identities if identities is not None else [[2, "synthetic"]],
        ),
    ]:
        with (raw / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(values)
    return raw


def test_temporal_split_preserves_ties_and_unmatched_rows(tmp_path):
    raw = source(tmp_path)
    result = module.run(raw, tmp_path / "output", "synthetic-test")
    assert result["unmatched_transactions"] == 3
    assert result["inputs"][0]["missing_blank_cells"]["feature"] == 1
    assert result["split"]["partitions"]["train"]["rows"] == 2
    assert result["split"]["partitions"]["validation"]["rows"] == 2
    assert result["split"]["partitions"]["train"]["fraud_rate"] == 0.5
    assert result["inputs"][0]["sha256"] == module.checksum(raw / "train_transaction.csv")
    assert (tmp_path / "output" / "EDA.md").exists()
    with (tmp_path / "output" / "split_membership.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 4


@pytest.mark.parametrize(
    "rows,identities",
    [
        ([[1, 0, 0, ""], [1, 1, 1, ""]], None),
        ([[1, "nan", 0, ""]], None),
        ([[1, 1, 2, ""]], None),
        (None, [[99, "synthetic"]]),
        (None, [[2, "synthetic"], [2, "synthetic"]]),
        ([[1, 1, 0, ""], [2, 1, 1, ""]], None),
    ],
)
def test_invalid_source_does_not_publish_output(tmp_path, rows, identities):
    raw = source(tmp_path, rows, identities)
    with pytest.raises(ValueError):
        module.run(raw, tmp_path / "output", "synthetic-test")
    assert not (tmp_path / "output").exists()


def test_refuses_overwrite(tmp_path):
    raw = source(tmp_path)
    with pytest.raises(ValueError, match="new directory"):
        module.run(raw, raw, "synthetic-test")

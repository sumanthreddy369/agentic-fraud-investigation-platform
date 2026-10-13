"""Training source validation uses synthetic records only."""

import csv
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
spec = importlib.util.spec_from_file_location(
    "training_baseline", Path(__file__).parents[1] / "scripts/train_ieee_baseline.py"
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def write_source(tmp_path, duplicate=False, label="0"):
    path = tmp_path / "synthetic.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["TransactionID", "TransactionDT", "isFraud", *baseline.FEATURES])
        for i in range(10):
            writer.writerow([0 if duplicate else i, i, label, "", *([1] * 14)])
    return path


def test_blank_sentinel_and_feature_order(tmp_path):
    x, y, times = baseline.load(write_source(tmp_path))
    assert x.shape == (10, 15)
    assert (x[:, 0] == -999).all()
    assert (x[:, 1:] == 1).all()
    assert times.tolist() == list(range(10))
    assert y.sum() == 0


@pytest.mark.parametrize("duplicate,label", [(True, "0"), (False, "unknown")])
def test_rejects_duplicate_ids_and_unknown_labels(tmp_path, duplicate, label):
    with pytest.raises(ValueError):
        baseline.load(write_source(tmp_path, duplicate, label))

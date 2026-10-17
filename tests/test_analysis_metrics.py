"""Check undefined rates and nonoverlapping reliability bins using synthetic labels."""

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from analyze_ieee_full import metrics, reliability  # noqa: E402


def test_reliability_includes_endpoints_exactly_once():
    p = np.array([0, 0.1, 0.3, 0.6, 0.7, 0.9, 1])
    y = np.array([0, 0, 1, 0, 1, 1, 1])
    bins = reliability(y, p)
    assert sum(b["rows"] for b in bins) == len(p)
    assert bins[-1]["rows"] == 2
    assert sum(b["observed"] * b["rows"] for b in bins) == y.sum()


def test_undefined_metrics_are_not_reported_as_success():
    result = metrics(np.zeros(4), np.zeros(4))
    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["precision"] is None
    assert result["recall"] is None
    assert result["tn"] == 4
    assert result["fp"] == 0


def test_confusion_counts_and_rates():
    result = metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.6, 0.4, 0.9]))
    assert [result[k] for k in ("tn", "fp", "fn", "tp")] == [1, 1, 1, 1]
    assert result["precision"] == result["recall"] == result["false_positive_rate"] == 0.5

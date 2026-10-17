"""Synthetic checks for review-capacity measurement and bounded calibration inputs."""

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from qualify_richer_numeric import logits, review_metrics  # noqa: E402


def test_threshold_ties_count_as_reviews():
    result = review_metrics(np.array([0, 1, 1, 0]), np.array([0.1, 0.5, 0.5, 0.9]), 0.5)
    assert result["reviewed"] == 3
    assert result["recall"] == 1
    assert result["precision"] == 2 / 3
    assert result["false_positive_rate"] == 0.5


def test_no_reviews_does_not_imply_perfect_precision():
    result = review_metrics(np.array([0, 1]), np.array([0.1, 0.2]), 0.9)
    assert result["precision"] is None
    assert result["recall"] == 0


def test_logit_handles_zero_and_one():
    transformed = logits(np.array([0, 0.5, 1]))
    assert np.isfinite(transformed).all()
    assert transformed[1, 0] == 0
    assert transformed[0, 0] < transformed[2, 0]

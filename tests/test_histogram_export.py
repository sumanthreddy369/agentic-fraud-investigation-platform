"""Conversion preserves missing-direction branches without changing installed libraries."""

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
ort = pytest.importorskip("onnxruntime")
pytest.importorskip("skl2onnx")
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from histogram_onnx import export_histogram  # noqa: E402
from package_richer_model import SENTINEL, wrap_missing  # noqa: E402


def test_histogram_missing_branch_parity():
    x = np.tile(np.array([[0, 1], [1, np.nan], [np.nan, 0], [2, 1]], dtype=np.float32), (30, 1))
    y = np.tile([0, 1, 1, 0], 30)
    model = HistGradientBoostingClassifier(max_iter=8, min_samples_leaf=2, random_state=42)
    model.fit(x, y)
    graph = export_histogram(model, 2)
    session = ort.InferenceSession(graph.SerializeToString(), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"features": x})[1][:, 1]
    np.testing.assert_allclose(actual, model.predict_proba(x)[:, 1], atol=1e-5, rtol=1e-5)


def test_finite_missing_wrapper_preserves_predictions():
    x = np.tile(np.array([[0, 1], [1, np.nan], [np.nan, 0], [2, 1]], dtype=np.float32), (30, 1))
    y = np.tile([0, 1, 1, 0], 30)
    model = HistGradientBoostingClassifier(max_iter=8, min_samples_leaf=2, random_state=42)
    model.fit(x, y)
    graph = wrap_missing(export_histogram(model, 2))
    session = ort.InferenceSession(graph.SerializeToString(), providers=["CPUExecutionProvider"])
    finite = np.where(np.isnan(x), SENTINEL, x)
    assert np.isfinite(finite).all()
    actual = session.run(None, {"features": finite})[1][:, 1]
    np.testing.assert_allclose(actual, model.predict_proba(x)[:, 1], atol=1e-5, rtol=1e-5)

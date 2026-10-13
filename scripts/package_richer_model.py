"""Package a parity-verified histogram graph with a finite missing-value contract."""

import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
from onnx import helper, numpy_helper

SENTINEL = np.finfo(np.float32).min


def wrap_missing(graph):
    input_name = graph.graph.input[0].name
    for node in graph.graph.node:
        for index, name in enumerate(node.input):
            if name == input_name:
                node.input[index] = "restored_missing_features"
    graph.graph.initializer.extend(
        [
            numpy_helper.from_array(np.array(SENTINEL, dtype=np.float32), "missing_sentinel"),
            numpy_helper.from_array(np.array(np.nan, dtype=np.float32), "missing_nan"),
        ]
    )
    graph.graph.node.insert(
        0, helper.make_node("Equal", [input_name, "missing_sentinel"], ["missing_mask"])
    )
    graph.graph.node.insert(
        1,
        helper.make_node(
            "Where", ["missing_mask", "missing_nan", input_name], ["restored_missing_features"]
        ),
    )
    onnx.checker.check_model(graph)
    return graph


def main():
    source = Path("artifacts/ieee_cis/richer-export-check-v2")
    proof = json.loads((source / "export-check.json").read_text())
    if proof.get("exported") is not True:
        raise ValueError("Native export parity must pass first")
    r = json.loads((source / "results.json").read_text())
    names = r["features"]
    raw = Path("data/raw/ieee_cis")
    tx = pd.read_csv(raw / "train_transaction.csv").select_dtypes("number")
    ident = pd.read_csv(raw / "train_identity.csv").select_dtypes("number")
    frame = tx.merge(ident, on="TransactionID", how="left", validate="one_to_one", sort=False)
    x = frame.loc[frame.TransactionDT >= r["boundaries"][2], names].to_numpy(dtype=np.float32)
    if np.isinf(x).any() or (x == SENTINEL).any():
        raise ValueError("Infinite source value or reserved sentinel collision")
    native = ort.InferenceSession(
        str(source / "candidate.onnx"), providers=["CPUExecutionProvider"]
    )
    expected = native.run(None, {"features": x})[1][:, 1]
    graph = wrap_missing(onnx.load(source / "candidate.onnx"))
    session = ort.InferenceSession(graph.SerializeToString(), providers=["CPUExecutionProvider"])
    finite = np.where(np.isnan(x), SENTINEL, x)
    actual = session.run(None, {"features": finite})[1][:, 1]
    np.testing.assert_allclose(actual, expected, atol=1e-5, rtol=1e-5)
    out = Path("artifacts/ieee_cis/model-v3")
    out.mkdir(exist_ok=False)
    binary = graph.SerializeToString()
    (out / "model.onnx").write_bytes(binary)
    schema = "ieee-numeric-400-floatmin-missing-v1"
    manifest = dict(
        domain="ieee_cis",
        model_version="ieee-hgb400-raw-v3",
        input_schema_version=schema,
        model_path="model.onnx",
        sha256=hashlib.sha256(binary).hexdigest(),
        feature_names=names,
        input_name="features",
        output_name=session.get_outputs()[1].name,
        output_kind="class_probabilities",
        positive_class="fraud",
        positive_class_index=1,
        providers=["CPUExecutionProvider"],
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    indices = np.linspace(0, len(x) - 1, 10, dtype=int)
    golden = [
        dict(
            request=dict(
                input_schema_version=schema,
                features=dict(zip(names, map(float, finite[i]), strict=True)),
            ),
            expected_probability=float(expected[i]),
        )
        for i in indices
    ]
    (out / "golden.json").write_text(json.dumps(golden, indent=2, allow_nan=False))
    result = dict(
        rows=len(x),
        max_missing_wrapper_error=float(np.max(abs(expected - actual))),
        native_export=proof,
        missing_sentinel=float(SENTINEL),
    )
    (out / "export-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()

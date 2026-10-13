"""Export the random-forest deployment fallback with sigmoid calibration in ONNX."""

import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
from onnx import helper, numpy_helper
from skl2onnx import to_onnx
from sklearn.ensemble import RandomForestClassifier
from train_ieee_baseline import FEATURES, SCHEMA, sha

folder = Path("artifacts/ieee_cis/full-analysis-v1")
r = json.loads((folder / "analysis.json").read_text())
if r["selected_by_selection_ap"] != "hist_gradient_boosting":
    raise ValueError("Unexpected selection")
source = Path("data/raw/ieee_cis/train_transaction.csv")
if sha(source) != r["source_sha256"]:
    raise ValueError("Source checksum differs from comparison dataset")
if Path("artifacts/ieee_cis/model-v2").exists():
    raise FileExistsError("Archive previous model-v2 outputs before exporting again")
df = pd.read_csv(
    "data/raw/ieee_cis/train_transaction.csv", usecols=FEATURES + ["TransactionDT", "isFraud"]
)
x = df[FEATURES].fillna(-999).to_numpy(dtype=np.float32)
y = df.isFraud.to_numpy()
mask = df.TransactionDT.to_numpy() < r["boundaries"][0]
model = RandomForestClassifier(
    n_estimators=40, max_depth=12, min_samples_leaf=20, n_jobs=2, random_state=42
)
model.fit(x[mask], y[mask])
graph = to_onnx(model, x[:1], options={id(model): {"zipmap": False}}, target_opset=17)
raw = graph.graph.output[1].name
cal = r["holdout"]["random_forest"]
for name, arr in [
    ("idx", np.array([1], dtype=np.int64)),
    ("low", np.array(1e-6, dtype=np.float32)),
    ("high", np.array(1 - 1e-6, dtype=np.float32)),
    ("one", np.array(1, dtype=np.float32)),
    ("slope", np.array(cal["calibration_slope"], dtype=np.float32)),
    ("intercept", np.array(cal["calibration_intercept"], dtype=np.float32)),
]:
    graph.graph.initializer.append(numpy_helper.from_array(arr, name="cal_" + name))
for op, inputs, output in [
    ("Gather", [raw, "cal_idx"], "positive"),
    ("Clip", ["positive", "cal_low", "cal_high"], "clipped"),
    ("Sub", ["cal_one", "clipped"], "negative"),
    ("Div", ["clipped", "negative"], "odds"),
    ("Log", ["odds"], "logit"),
    ("Mul", ["logit", "cal_slope"], "scaled"),
    ("Add", ["scaled", "cal_intercept"], "shifted"),
    ("Sigmoid", ["shifted"], "calibrated"),
]:
    graph.graph.node.append(
        helper.make_node(op, inputs, [output], **({"axis": 1} if op == "Gather" else {}))
    )
del graph.graph.output[:]
graph.graph.output.append(
    helper.make_tensor_value_info("calibrated", onnx.TensorProto.FLOAT, [None, 1])
)
onnx.checker.check_model(graph)
session = ort.InferenceSession(graph.SerializeToString(), providers=["CPUExecutionProvider"])
test = df.TransactionDT.to_numpy() >= r["boundaries"][2]
p = model.predict_proba(x[test])[:, 1]
clipped = np.clip(p, 1e-6, 1 - 1e-6)
expected = 1 / (
    1
    + np.exp(
        -(np.log(clipped / (1 - clipped)) * cal["calibration_slope"] + cal["calibration_intercept"])
    )
)
actual = session.run(None, {session.get_inputs()[0].name: x[test]})[0].reshape(-1)
np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)
out = Path("artifacts/ieee_cis/model-v2")
out.mkdir(exist_ok=False)
(out / "model.onnx").write_bytes(graph.SerializeToString())
manifest = dict(
    domain="ieee_cis",
    model_version="ieee-rf15-sigmoid-v2",
    input_schema_version=SCHEMA,
    model_path="model.onnx",
    sha256=sha(out / "model.onnx"),
    feature_names=FEATURES,
    input_name=session.get_inputs()[0].name,
    output_name="calibrated",
    output_kind="probability",
    positive_class="fraud",
    positive_class_index=0,
    providers=["CPUExecutionProvider"],
)
(out / "manifest.json").write_text(json.dumps(manifest, indent=2))
golden = [
    {
        "request": {
            "input_schema_version": SCHEMA,
            "features": dict(zip(FEATURES, map(float, row), strict=True)),
        },
        "expected_probability": float(value),
    }
    for row, value in zip(x[test][:10], expected[:10], strict=True)
]
(out / "golden.json").write_text(json.dumps(golden, indent=2))
(out / "export-verification.json").write_text(
    json.dumps(
        {
            "rows": int(test.sum()),
            "maximum_absolute_error": float(np.max(abs(expected - actual))),
            "source_report": "full-analysis-v1/analysis.json",
        },
        indent=2,
    )
)
print("Calibrated random-forest fallback passed parity on all audit rows")

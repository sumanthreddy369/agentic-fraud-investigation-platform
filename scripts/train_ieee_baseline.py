"""Train a deliberately small IEEE-CIS numeric baseline and verify its ONNX export."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from skl2onnx import to_onnx
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)

FEATURES = ["TransactionAmt"] + [f"C{i}" for i in range(1, 15)]
SCHEMA = "ieee-numeric-15-sentinel-v1"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def load(path):
    features, labels, times = [], [], []
    keys = set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not set(FEATURES + ["TransactionID", "TransactionDT", "isFraud"]) <= set(
            reader.fieldnames or []
        ):
            raise ValueError("Source schema mismatch")
        for row in reader:
            key = row["TransactionID"]
            if key in keys:
                raise ValueError("Duplicate transaction")
            keys.add(key)
            if row["isFraud"] not in {"0", "1"}:
                raise ValueError("Invalid label")
            values = [float(row[n]) if row[n].strip() else -999.0 for n in FEATURES]
            dt = float(row["TransactionDT"])
            if not np.isfinite(values).all() or not np.isfinite(dt) or dt < 0:
                raise ValueError("Invalid numeric value")
            features.append(values)
            times.append(dt)
            labels.append(int(row["isFraud"]))
    x = np.asarray(features, dtype=np.float32)
    if not np.isfinite(x).all() or len(x) < 10:
        raise ValueError("Invalid or insufficient input")
    return x, np.asarray(labels), np.asarray(times)


def train(source: Path, output: Path):
    if output.exists():
        raise ValueError("Use a new output directory")
    source_hash = sha(source)
    x, y, times = load(source)
    if sha(source) != source_hash:
        raise ValueError("Source changed")
    boundary = np.sort(times)[int(len(times) * 0.8)]
    mask = times < boundary
    if len(np.unique(y[mask])) != 2 or len(np.unique(y[~mask])) != 2:
        raise ValueError("Both partitions must contain both labels")
    model = RandomForestClassifier(
        n_estimators=40, max_depth=12, min_samples_leaf=20, n_jobs=2, random_state=42
    )
    print("Fitting baseline on chronological training partition", flush=True)
    model.fit(x[mask], y[mask])
    prob = model.predict_proba(x[~mask])[:, 1]
    graph = to_onnx(model, x[:1], options={id(model): {"zipmap": False}}, target_opset=17)
    session = ort.InferenceSession(graph.SerializeToString(), providers=["CPUExecutionProvider"])
    output_name = session.get_outputs()[1].name
    exported = session.run([output_name], {session.get_inputs()[0].name: x[~mask]})[0][:, 1]
    max_error = float(np.max(np.abs(prob - exported)))
    if not np.allclose(prob, exported, rtol=1e-5, atol=1e-5):
        raise ValueError("ONNX parity failed")
    tn, fp, fn, tp = confusion_matrix(y[~mask], exported >= 0.5, labels=[0, 1]).ravel()
    report = {
        "model_version": "ieee-rf-numeric15-v1",
        "source_sha256": source_hash,
        "features": FEATURES,
        "missing_value": -999.0,
        "split_boundary": float(boundary),
        "train_rows": int(mask.sum()),
        "validation_rows": int((~mask).sum()),
        "train_fraud_rate": float(y[mask].mean()),
        "validation_fraud_rate": float(y[~mask].mean()),
        "roc_auc": float(roc_auc_score(y[~mask], exported)),
        "average_precision": float(average_precision_score(y[~mask], exported)),
        "brier_score": float(brier_score_loss(y[~mask], exported)),
        "threshold": 0.5,
        "precision": float(tp / max(tp + fp, 1)),
        "recall": float(tp / max(tp + fn, 1)),
        "false_positive_rate": float(fp / max(fp + tn, 1)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "onnx_max_absolute_error": max_error,
        "parity_tolerance": {"atol": 1e-5, "rtol": 1e-5},
        "hyperparameters": model.get_params(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ["numpy", "scikit-learn", "skl2onnx", "onnxruntime"]
        },
        "limitations": [
            "New educational baseline; not an existing portfolio model",
            "Only amount and C1-C14; no identity or categorical features",
            "Fixed blank sentinel; no learned preprocessing",
            "Uncalibrated probabilities; threshold is fixed, not optimized",
            "No independent final test or subgroup validation; no deployment approval",
        ],
    }
    output.mkdir(parents=True)
    (output / "model.onnx").write_bytes(graph.SerializeToString())
    manifest = {
        "domain": "ieee_cis",
        "model_version": report["model_version"],
        "input_schema_version": SCHEMA,
        "model_path": "model.onnx",
        "sha256": sha(output / "model.onnx"),
        "feature_names": FEATURES,
        "input_name": session.get_inputs()[0].name,
        "output_name": output_name,
        "output_kind": "class_probabilities",
        "positive_class": "fraud",
        "positive_class_index": 1,
        "providers": ["CPUExecutionProvider"],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Private golden fixtures stay in ignored artifacts, never the public repository.
    indices = np.flatnonzero(~mask)[:10]
    golden = [
        {
            "request": {
                "input_schema_version": SCHEMA,
                "features": dict(zip(FEATURES, map(float, x[i]), strict=True)),
            },
            "expected_probability": float(model.predict_proba(x[i : i + 1])[0, 1]),
        }
        for i in indices
    ]
    (output / "golden.json").write_text(json.dumps(golden, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "train_rows",
                    "validation_rows",
                    "roc_auc",
                    "average_precision",
                    "onnx_max_absolute_error",
                ]
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    train(args.source, args.output)

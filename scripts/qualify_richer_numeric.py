"""Bounded richer-numeric candidate; retrospective research only, never auto-promoted."""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from analyze_ieee_full import metrics, reliability
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix


def review_metrics(y, p, threshold):
    tn, fp, fn, tp = confusion_matrix(y, p >= threshold, labels=[0, 1]).ravel()
    return dict(
        threshold=float(threshold),
        rows=len(y),
        reviewed=int(tp + fp),
        review_fraction=float((tp + fp) / len(y)),
        precision=float(tp / (tp + fp)) if tp + fp else None,
        recall=float(tp / (tp + fn)) if tp + fn else None,
        false_positive_rate=float(fp / (fp + tn)) if fp + tn else None,
    )


def logits(p):
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def main():
    out = Path("artifacts/ieee_cis/richer-qualification-v1")
    out.mkdir(parents=True, exist_ok=False)
    reference = json.loads(Path("artifacts/ieee_cis/full-analysis-v1/analysis.json").read_text())
    print("Reading transactions and validating identity join", flush=True)
    raw = Path("data/raw/ieee_cis")
    transactions = pd.read_csv(raw / "train_transaction.csv")
    identity = pd.read_csv(raw / "train_identity.csv").select_dtypes("number")
    if transactions.TransactionID.duplicated().any() or identity.TransactionID.duplicated().any():
        raise ValueError("Duplicate source keys")
    if not identity.TransactionID.isin(transactions.TransactionID).all():
        raise ValueError("Orphan identity keys")
    frame = transactions.select_dtypes("number").merge(
        identity, on="TransactionID", how="left", validate="one_to_one", sort=False
    )
    assert len(frame) == len(transactions)
    features = sorted(set(frame.columns) - {"TransactionID", "TransactionDT", "isFraud"})
    x = frame[features].to_numpy(dtype=np.float32)
    if np.isinf(x).any():
        raise ValueError("Infinite features")
    y = frame.isFraud.to_numpy()
    if not np.isin(y, [0, 1]).all():
        raise ValueError("Invalid labels")
    t = frame.TransactionDT.to_numpy()
    b = reference["boundaries"]
    train = t < b[0]
    selection = (t >= b[0]) & (t < b[1])
    audit = t >= b[2]
    calibration = (t >= b[1]) & (t < b[2])
    groups = transactions.loc[audit, ["ProductCD", "card4", "card6"]].reset_index(drop=True)
    del transactions, identity, frame
    model = HistGradientBoostingClassifier(
        max_iter=100, max_leaf_nodes=15, random_state=42, early_stopping=False
    )
    print(f"Training bounded histogram candidate with {len(features)} numeric features", flush=True)
    start = time.perf_counter()
    model.fit(x[train], y[train])
    fit_seconds = time.perf_counter() - start
    cp = model.predict_proba(x[calibration])[:, 1]
    ap = model.predict_proba(x[audit])[:, 1]
    sp = model.predict_proba(x[selection])[:, 1]
    calibrator = LogisticRegression(C=1e6, max_iter=1000)
    calibrator.fit(logits(cp), y[calibration])
    calibrated = calibrator.predict_proba(logits(ap))[:, 1]
    policies = []
    for capacity in [0.01, 0.03, 0.05]:
        threshold = np.quantile(sp, 1 - capacity, method="higher")
        policies.append(
            dict(
                target_review_fraction=capacity,
                selection=review_metrics(y[selection], sp, threshold),
                audit=review_metrics(y[audit], ap, threshold),
            )
        )
    subgroups = {}
    for column in groups:
        subgroups[column] = []
        for name, rows in groups.groupby(column, dropna=False):
            indices = rows.index.to_numpy()
            if len(indices) >= 100:
                subgroups[column].append(
                    dict(
                        group=str(name),
                        positives=int(y[audit][indices].sum()),
                        raw=metrics(y[audit][indices], ap[indices]),
                        calibrated=metrics(y[audit][indices], calibrated[indices]),
                    )
                )
    result = {
        "calibration_rows": int(calibration.sum()),
        "calibrated_audit": metrics(y[audit], calibrated),
        "calibration_slope": float(calibrator.coef_[0, 0]),
        "calibration_intercept": float(calibrator.intercept_[0]),
        "review_policies_raw": policies,
        "subgroups": subgroups,
        "reliability": {
            "raw": reliability(y[audit], ap),
            "sigmoid": reliability(y[audit], calibrated),
        },
        "features": features,
        "boundaries": b,
        "fit_seconds": fit_seconds,
        "training_rows": int(train.sum()),
        "selection": metrics(y[selection], model.predict_proba(x[selection])[:, 1]),
        "audit": metrics(y[audit], model.predict_proba(x[audit])[:, 1]),
        "status": "research candidate, not exported or promoted",
        "limitations": [
            "Previously examined audit period; not an independent final test",
            "Numeric-only candidate; categorical features not included",
            "Identity timing and anonymized feature availability require validation",
            "Calibration and capacity scenarios evaluated; no policy approved or ONNX export",
            "Missing values handled natively; no future aggregate or label-derived features",
            "Feature names chosen by numeric schema, not audit performance",
        ],
    }
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"features", "subgroups", "reliability"}}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

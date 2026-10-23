"""Bounded richer-numeric candidate; retrospective research only, never auto-promoted."""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from analyze_ieee_full import metrics
from sklearn.ensemble import HistGradientBoostingClassifier


def main():
    out = Path("artifacts/ieee_cis/richer-numeric-v1")
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
    del transactions, identity, frame
    model = HistGradientBoostingClassifier(
        max_iter=100, max_leaf_nodes=15, random_state=42, early_stopping=False
    )
    print(f"Training bounded histogram candidate with {len(features)} numeric features", flush=True)
    start = time.perf_counter()
    model.fit(x[train], y[train])
    fit_seconds = time.perf_counter() - start
    result = {
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
            "No fitted calibration, operating threshold, ONNX export or production approval",
            "Missing values handled natively; no future aggregate or label-derived features",
            "Feature names chosen by numeric schema, not audit performance",
        ],
    }
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "features"}), flush=True)


if __name__ == "__main__":
    main()

"""Reproducible IEEE-CIS exploration, temporal model comparison and calibration."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from train_ieee_baseline import FEATURES


def metrics(y, p):
    tn, fp, fn, tp = confusion_matrix(y, p >= 0.5, labels=[0, 1]).ravel()
    return dict(
        rows=len(y),
        prevalence=float(np.mean(y)),
        roc_auc=float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        average_precision=float(average_precision_score(y, p)) if np.sum(y) else None,
        brier=float(brier_score_loss(y, p)),
        log_loss=float(log_loss(y, p, labels=[0, 1])),
        precision=float(tp / (tp + fp)) if tp + fp else None,
        recall=float(tp / (tp + fn)) if tp + fn else None,
        false_positive_rate=float(fp / (fp + tn)) if fp + tn else None,
        tn=int(tn),
        fp=int(fp),
        fn=int(fn),
        tp=int(tp),
    )


def reliability(y, p):
    result = []
    indices = np.minimum((p * 10).astype(int), 9)
    for index in range(10):
        lo = index / 10
        mask = indices == index
        if mask.any():
            result.append(
                dict(
                    lower=float(lo),
                    rows=int(mask.sum()),
                    mean_prediction=float(p[mask].mean()),
                    observed=float(y[mask].mean()),
                )
            )
    return result


def run(raw, out):
    out.mkdir(parents=True, exist_ok=False)
    print("Reading full transaction training table", flush=True)
    df = pd.read_csv(raw / "train_transaction.csv")
    if df.TransactionID.duplicated().any() or not df.isFraud.isin([0, 1]).all():
        raise ValueError("Invalid keys or labels")
    df.describe(include="all").to_csv(out / "column_statistics.csv")
    pd.DataFrame(
        {
            "missing": df.isna().sum(),
            "missing_fraction": df.isna().mean(),
            "unique_nonmissing": df.nunique(),
            "dtype": df.dtypes.astype(str),
        }
    ).to_csv(out / "column_quality.csv")
    # Selected serving-feature correlations use all training-source rows, pairwise complete.
    df[FEATURES + ["isFraud"]].corr().to_csv(out / "serving_feature_correlations.csv")
    sample = df.sample(n=min(50000, len(df)), random_state=42)
    sample.select_dtypes("number").drop(columns=["TransactionID"]).corr().to_csv(
        out / "all_numeric_correlations_sample50000.csv"
    )
    for col in ["ProductCD", "card4", "card6", "P_emaildomain"]:
        summary = df.groupby(col, dropna=False).isFraud.agg(["size", "mean"])
        summary.to_csv(out / f"category_{col}.csv")
    ident = pd.read_csv(raw / "train_identity.csv")
    if ident.TransactionID.duplicated().any():
        raise ValueError("Duplicate identity keys")
    if not ident.TransactionID.isin(df.TransactionID).all():
        raise ValueError("Orphan identities")
    ident.describe(include="all").to_csv(out / "identity_statistics.csv")
    pd.DataFrame(
        {
            "missing": ident.isna().sum(),
            "fraction": ident.isna().mean(),
            "unique_nonmissing": ident.nunique(),
        }
    ).to_csv(out / "identity_quality.csv")
    df["identity_present"] = df.TransactionID.isin(ident.TransactionID)
    device = ident.set_index("TransactionID").DeviceType
    df["DeviceType"] = df.TransactionID.map(device).fillna("missing")
    boundaries = np.quantile(df.TransactionDT, [0.6, 0.7, 0.8], method="higher")
    t = df.TransactionDT.to_numpy()
    masks = [
        t < boundaries[0],
        (t >= boundaries[0]) & (t < boundaries[1]),
        (t >= boundaries[1]) & (t < boundaries[2]),
        t >= boundaries[2],
    ]
    x = df[FEATURES].fillna(-999).to_numpy(dtype=np.float32)
    y = df.isFraud.to_numpy()
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite features")
    models = {
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000, random_state=42)
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=40, max_depth=12, min_samples_leaf=20, n_jobs=2, random_state=42
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=100, max_leaf_nodes=15, random_state=42
        ),
    }
    selection = {}
    fitted = {}
    for name, model in models.items():
        print("Training " + name, flush=True)
        start = time.perf_counter()
        model.fit(x[masks[0]], y[masks[0]])
        p = model.predict_proba(x[masks[1]])[:, 1]
        selection[name] = metrics(y[masks[1]], p)
        selection[name]["fit_seconds"] = time.perf_counter() - start
        fitted[name] = model
    winner = max(selection, key=lambda n: selection[n]["average_precision"])
    print("Selection winner " + winner, flush=True)
    results = {}
    bins = {}
    subgroups = {}
    for name, model in fitted.items():
        cp = model.predict_proba(x[masks[2]])[:, 1]
        hp = model.predict_proba(x[masks[3]])[:, 1]

        # Sigmoid calibration fits only the distinct calibration partition.
        def logits(p):
            return np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(
                -1, 1
            )

        calibrator = LogisticRegression(C=1e6, max_iter=1000)
        calibrator.fit(logits(cp), y[masks[2]])
        calibrated = calibrator.predict_proba(logits(hp))[:, 1]
        results[name] = {
            "raw": metrics(y[masks[3]], hp),
            "sigmoid": metrics(y[masks[3]], calibrated),
            "calibration_slope": float(calibrator.coef_[0, 0]),
            "calibration_intercept": float(calibrator.intercept_[0]),
        }
        bins[name] = {
            "raw": reliability(y[masks[3]], hp),
            "sigmoid": reliability(y[masks[3]], calibrated),
        }
        if name == winner:
            audit = df.loc[masks[3]].copy()
            audit["probability"] = calibrated
            for col in ["ProductCD", "card4", "card6", "DeviceType", "identity_present"]:
                subgroups[col] = []
                for group, frame in audit.groupby(col, dropna=False):
                    if len(frame) < 100:
                        continue
                    subgroups[col].append(
                        {
                            "group": str(group),
                            **metrics(frame.isFraud.to_numpy(), frame.probability.to_numpy()),
                        }
                    )
            pred = pd.DataFrame(
                {
                    "TransactionID": audit.TransactionID,
                    "label": audit.isFraud,
                    "raw_probability": hp,
                    "calibrated_probability": calibrated,
                }
            )
            pred.to_csv(out / "private_holdout_predictions.csv", index=False)
    prior = np.full(masks[3].sum(), y[masks[0]].mean())
    results["constant_prior"] = {"raw": metrics(y[masks[3]], prior)}
    # Unlabeled test data supports schema and drift checks, never performance claims.
    test = pd.read_csv(
        raw / "test_transaction.csv", usecols=["TransactionID", "TransactionDT", *FEATURES]
    )
    if test.TransactionID.duplicated().any() or test.TransactionID.isin(df.TransactionID).any():
        raise ValueError("Invalid test IDs")
    test[FEATURES + ["TransactionDT"]].describe().to_csv(out / "unlabeled_test_statistics.csv")
    report = {
        "boundaries": boundaries.tolist(),
        "partitions": dict(
            zip(
                ["train", "selection", "calibration", "audit_holdout"],
                [int(m.sum()) for m in masks],
                strict=True,
            )
        ),
        "selection": selection,
        "selected_by_selection_ap": winner,
        "holdout": results,
        "reliability": bins,
        "subgroups": subgroups,
        "test_rows": len(test),
        "caveats": [
            "Audit holdout was previously evaluated by baseline v1; not a pristine final test",
            "All models use the same 15 numeric features; no claim of global best model",
            "Calibration chosen in advance, not selected using holdout metrics",
            "Business categories are not protected demographic groups; no fairness certification",
            "All-column correlations use a seeded 50000-row sample; "
            "serving-feature correlations use all rows",
            "No automated enforcement; probabilities need independent prospective validation",
        ],
    }
    with (raw / "train_transaction.csv").open("rb") as f:
        report["source_sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
    (out / "analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps({"winner": winner, "partitions": report["partitions"], "holdout": results}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.raw, args.output)

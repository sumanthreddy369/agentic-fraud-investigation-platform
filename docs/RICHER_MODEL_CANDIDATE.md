# Richer numeric fraud candidate

Executed locally October 13, 2026. Research candidate only; not deployed or promoted.

## Experiment

Histogram gradient boosting: 100 iterations, 15 leaves, random seed 42,
early stopping disabled, two OpenMP threads. Left-joined numeric identity features
one-to-one onto transactions, preserving unmatched transactions and original row count.
Used 400 numeric features; excluded TransactionID, TransactionDT and isFraud from inputs.
Missing values are handled natively. No categorical encoding or future aggregates.
Training used 354,324 rows and the earlier frozen chronological boundaries.
Fit time was 33.78 seconds on this laptop; this is not serving latency.

## Measured comparison

| Model | Selection AP | Audit ROC AUC | Audit AP | Audit Brier | Audit recall at 0.5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prior 15-feature histogram, raw | 0.5005 | 0.8395 | 0.4065 | 0.02535 | 0.2608 |
| Richer 400-feature histogram, raw | 0.5752 | 0.8716 | 0.4401 | 0.02459 | 0.2884 |

Richer audit precision: 0.7404; false-positive rate: 0.0036.
Confusion counts: TN 113633, FP 411, FN 2892, TP 1172.
Same chronological partitions, but both features and preprocessing changed: the earlier
candidate used -999 missing encoding and default early stopping. This is a candidate
comparison, not a controlled estimate of the benefit of feature count alone.

## Qualification still required

The audit period was previously examined. These are retrospective results, not
independent evidence of production performance. Identity availability at scoring time
and anonymized feature semantics are unverified. Calibration, operating thresholds,
subgroup analysis for this candidate, temporal stability, uncertainty estimates and
ONNX conversion/parity were outside this experiment. No model binary from this experiment was saved
or promoted; the prior verified ONNX baseline remains unchanged.

## Reproduce

```powershell
$env:OMP_NUM_THREADS='2'
uv run --extra training --extra onnx-cpu python scripts/train_richer_numeric.py
```

Requires approved source CSVs and the earlier analysis.json boundary manifest.
The output folder must not already exist. Private aggregate JSON and feature inventory
are saved in artifacts/ieee_cis/richer-numeric-v1; raw rows are not published.

[Training code](../scripts/train_richer_numeric.py) | [Evidence gallery](MILESTONE_GALLERY.md)

Calibration, validation-defined review scenarios and business-subgroup evaluation are now recorded in [the qualification report](RICHER_MODEL_QUALIFICATION.md). Local serving qualification followed in [the ONNX and API report](RICHER_MODEL_SERVING.md).

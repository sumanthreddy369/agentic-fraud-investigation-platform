# IEEE CIS numeric baseline

On October 13, 2026, a new educational random-forest baseline was trained locally on
the official IEEE-CIS training transactions. This is not a recovered portfolio model
and is not approved for production decisions.

## Reproduce

```powershell
uv sync --frozen --extra training --extra onnx-cpu
uv run python scripts/train_ieee_baseline.py --source data/raw/ieee_cis/train_transaction.csv --output artifacts/ieee_cis/model-v1
uv run python scripts/verify_model_api.py --model-dir artifacts/ieee_cis/model-v1
```

Use a new output directory for every run. The saved program checks required columns,
duplicate IDs, binary labels, finite values, and source-file stability. It uses amount
and C1 through C14, with blank values represented by -999. This fixed transformation
has no fitted statistics. API clients must apply that same blank-value convention and
provide exactly the manifest's 15 numeric features under `ieee-numeric-15-sentinel-v1`.
Identity and categorical features are not included. Relative time is used only for splitting.

The model has 40 trees, maximum depth 12, minimum leaf size 20, two CPU workers, and
seed 42. Rows before relative time 12192900 train the model; later rows, including
ties at the boundary, form validation. No threshold or hyperparameter search was
performed against validation. Dependency versions are locked in uv.lock and recorded
with the artifact. Models, source data, and golden feature payloads stay outside Git.

## Measured results

| Measure | Value |
| --- | ---: |
| Training rows | 472432 |
| Validation rows | 118108 |
| Validation fraud prevalence | 3.44% |
| ROC AUC | 0.8469 |
| Average precision | 0.4273 |
| Brier score | 0.02474 |
| Precision at threshold 0.5 | 82.46% |
| Recall at threshold 0.5 | 24.29% |
| False positive rate at threshold 0.5 | 0.184% |
| Maximum original versus ONNX probability difference | 1.03e-7 or less |

The fixed 0.5 threshold misses approximately three quarters of fraud in validation.
These results justify a serving demonstration, not an enforcement policy. Probabilities
are uncalibrated. Future work includes training-only feature engineering, separate
calibration and final evaluation partitions, subgroup checks, and capacity-based
threshold selection. Average precision is reported explicitly rather than equated
with trapezoidal area under a precision-recall curve.

## Saved artifacts and verification

`artifacts/ieee_cis/model-v1/` contains model.onnx, manifest.json, evaluation.json,
golden.json, and api-verification.json. The export checks parity across all validation
rows with predeclared absolute and relative tolerances of 1e-5. The checksum-pinned
adapter was exercised through FastAPI on ten private golden requests; all passed.
Unauthenticated requests and an incorrect schema were rejected. The existing gateway
returns a generic 502 for adapter schema mismatch; no score is returned.

Focused training-input, API, and ONNX tests: 36 passed, 1 skipped (optional provider).
The image `risk-platform:ieee-v1` also built successfully and passed ten actual HTTP
golden predictions through `scripts/verify_model_container.py`; its temporary container
was stopped afterward. Results are in `container-verification.json`. Database readiness,
Kubernetes recovery, scaling, and infrastructure reproducibility remain unverified.

# Richer candidate qualification

Executed October 13, 2026. Local retrospective evaluation; not production approval.

Refit the fixed 400-feature histogram candidate on the same 354,324 training rows. Sigmoid calibration used only the separate 59,054-row calibration period. Review thresholds were computed from raw selection-period scores without consulting audit outcomes. Tied scores can exceed nominal review capacity.

## Calibration on 118,108 audit rows

| Output | ROC AUC | AP | Brier | Log loss |
| --- | ---: | ---: | ---: | ---: |
| Raw | 0.8716 | 0.4401 | 0.02459 | 0.10285 |
| Sigmoid | 0.8716 | 0.4401 | 0.02478 | 0.10326 |

## Fixed review thresholds

These are illustrative workload scenarios, not approved company policies. No threshold was chosen using audit performance.

| Selection target | Threshold | Selection review rate | Audit review rate | Audit precision | Audit recall | Audit FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1% | 0.863158 | 1.00% | 0.70% | 90.53% | 18.36% | 0.07% |
| 3% | 0.211882 | 3.00% | 2.74% | 49.07% | 39.07% | 1.45% |
| 5% | 0.116912 | 5.00% | 5.22% | 31.21% | 47.37% | 3.72% |

## Business subgroups: raw output at threshold 0.5

Groups with fewer than 100 rows are omitted. These are not demographic fairness assessments; counts are provided to expose unstable estimates.

| Dimension | Group | Rows | Fraud positives | AP | Recall | FPR |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ProductCD | C | 12109 | 1617 | 0.7343 | 0.5628 | 0.0220 |
| ProductCD | H | 3333 | 197 | 0.5524 | 0.3046 | 0.0061 |
| ProductCD | R | 5496 | 257 | 0.7735 | 0.5447 | 0.0032 |
| ProductCD | S | 3501 | 183 | 0.3074 | 0.2459 | 0.0075 |
| ProductCD | W | 93669 | 1810 | 0.0934 | 0.0094 | 0.0013 |
| card4 | american express | 1126 | 33 | 0.4475 | 0.2424 | 0.0046 |
| card4 | discover | 1257 | 113 | 0.3259 | 0.1150 | 0.0044 |
| card4 | mastercard | 38355 | 1230 | 0.4710 | 0.3472 | 0.0041 |
| card4 | visa | 76626 | 2673 | 0.4392 | 0.2671 | 0.0032 |
| card4 | nan | 744 | 15 | 0.4986 | 0.6667 | 0.0219 |
| card6 | credit | 27270 | 1761 | 0.5256 | 0.3543 | 0.0072 |
| card6 | debit | 90095 | 2288 | 0.3742 | 0.2351 | 0.0024 |
| card6 | nan | 743 | 15 | 0.4987 | 0.6667 | 0.0220 |

## Reproduction and remaining gates

Run `uv run --extra training --extra onnx-cpu python scripts/qualify_richer_numeric.py` from the repository root with OMP_NUM_THREADS=2. Requires approved source CSVs and the earlier boundary manifest; output folder must not already exist. Private JSON includes raw/calibrated subgroup metrics and reliability bins.

Six focused tests passed for threshold ties, no-review precision, finite logit endpoints and metric calculations. Ruff lint/format passed.

The audit period was already examined. Identity availability, source feature semantics, categorical inputs, uncertainty, temporal stability, inference latency, ONNX export and parity remain incomplete. Neither calibration nor a policy is automatically promoted from this audit. The serving model remains the verified 15-feature random forest. No AWS compute was created for this run.

Update: [richer-model ONNX export and local API qualification](RICHER_MODEL_SERVING.md) now pass. This supersedes the earlier export status. Cloud deployment and production approval remain incomplete.

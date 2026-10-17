# Verified portfolio metrics

## Resume entry

**Fraud Risk Scoring Platform — 590K Transactions**

Python, pandas, scikit-learn, ONNX Runtime, FastAPI, PostgreSQL, Docker,
Kubernetes, Terraform and GitHub Actions. Kubernetes application evidence is local;
the first AWS attempt did not produce working worker nodes.

- Analyzed 590,540 IEEE-CIS transactions for missingness, feature distributions,
  correlations and business-category fraud rates using chronological evaluation splits.
- Compared logistic regression, random forest and histogram gradient boosting;
  qualified a richer 400-feature candidate with audit ROC-AUC 0.8716 and average
  precision 0.4401 across 118,108 retrospective transactions.
- Evaluated validation-defined review thresholds: one scenario flagged 0.70% of
  audit transactions at 90.53% precision and 18.36% fraud recall.
- Verified Python-to-ONNX score parity on 118,108 records with maximum absolute
  error 3.37e-7, and passed 10 protected API golden-prediction checks.
- Completed 60 of 60 bounded replay requests across three local Docker replicas
  with no retries, exact reference prediction parity and HTTP p95 of 117.82 ms.

## Model comparison

| Raw model | Features | Audit ROC-AUC | Audit average precision |
| --- | ---: | ---: | ---: |
| Logistic regression | 15 | 0.7093 | 0.1627 |
| Random forest | 15 | 0.8357 | 0.4021 |
| Histogram gradient boosting | 15 | 0.8395 | 0.4065 |
| Richer histogram gradient boosting | 400 | 0.8716 | 0.4401 |

The richer candidate's average precision increased approximately 8.3% relatively
against the 15-feature histogram candidate. Features and preprocessing both changed;
this is not a controlled estimate of the effect of adding features alone.

## Explain the numbers in an interview

| Metric | Meaning and boundary |
| --- | --- |
| 354,324 training rows | 60% of the labeled transactions, ordered chronologically |
| 59,054 selection rows | Separate period for candidate and review-threshold selection |
| 59,054 calibration rows | Separate period used to fit sigmoid calibration |
| 118,108 audit rows | Previously examined retrospective period, not a pristine prospective holdout |
| ROC-AUC 0.8716 | Ranking discrimination, not 87.16% classification accuracy |
| Average precision 0.4401 | Precision-recall summary; not trapezoidal PR-AUC |
| Precision 74.04% at 0.5 | Fraction of flagged transactions that were fraudulent |
| Recall 28.84% at 0.5 | Fraction of fraudulent transactions detected |
| False-positive rate 0.36% at 0.5 | Fraction of legitimate transactions incorrectly flagged |
| HTTP p95 117.82 ms | Short laptop Docker replay; excludes queue waiting |
| End-to-end p95 386.42 ms | Same replay including admission and queue waiting |

At threshold 0.5, the richer model produced 1,172 true positives, 411 false positives,
2,892 false negatives and 113,633 true negatives. This exposes the recall limitation
instead of hiding it behind overall accuracy. No measured loss savings, production
SLA, or reduction in human work has been established.

The replay repeated ten golden payloads six times. Its observed 30.21 requests/second
over 1.99 seconds is not a sustained throughput or AWS performance guarantee.
LangGraph, MCP and external model-provider integrations remain targets.

## Evidence

- [Full EDA and baseline comparison](FULL_EDA_COMPARISON.md)
- [Richer candidate](RICHER_MODEL_CANDIDATE.md)
- [Calibration, thresholds and subgroups](RICHER_MODEL_QUALIFICATION.md)
- [ONNX and API qualification](RICHER_MODEL_SERVING.md)
- [Three-replica replay](REPLICA_REPLAY_RESULTS.md)
- [AWS deployment attempt](AWS_EXECUTION_20261015.md)

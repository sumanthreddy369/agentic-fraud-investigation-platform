# Baseline inventory

Inspected read-only before implementation. These are related repositories; a complete authoritative AWS Risk Portfolio checkout has not yet been supplied.

| Domain | Source revision | Observed source | Artifact status |
| --- | --- | --- | --- |
| IEEE-CIS | `Financial-Transaction-Fraud-Detection-on-AWS` at `4994622381ee1e811773177c17fc92f86cf3fb4a` | Combined `Code` training/preprocessing example; `utils.py`; `requirements.txt`. Training references `sample_data.csv`, `config.yaml`, and `models/{best_name}.joblib`. | Referenced model and dataset are absent from inspected Git tree. README describes XGBoost while example code trains scikit-learn gradient boosting. Actual model/version remains unresolved. |
| Home Credit | `Credit-Risk-Loan-Default-Prediction` at `a1c4154698094a811c582ee5c48c590b67b875d4` | `code` contains preprocessing. README describes LightGBM and SHAP. | No trained artifact or dataset found in inspected Git tree. |
| Elliptic | `-Graph-Based-Fraud-Ring-Detection` at `6e80be87fa5a4a913f715ca86311225d537a70a2` | `code` draws a graph from `sample_graph.csv`; imported `graph_builder` is missing from inspected tree. | No saved classifier or dataset found in inspected Git tree. |

README metrics are unverified reported results, not reproduced baselines. No model binary has been deserialized, no training run performed, and no dataset relocated.

## Required adapter acceptance evidence

For each domain, record the authoritative endpoint or artifact URI, source commit, artifact SHA-256 or S3 version ID, trusted provenance, preprocessing artifacts, feature order/dtypes, positive-class mapping, missing-value semantics, dependency lock, and golden input/output fixtures. Keep private artifact paths and credentials outside Git. Verify inference parity before exposing the adapter.

The initial registry marks every model unavailable. Its protocol is an extension boundary, not an assertion that the existing models have been integrated.

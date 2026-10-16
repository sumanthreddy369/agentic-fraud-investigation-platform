# Local IEEE-CIS onboarding

The first source is the official IEEE-CIS Fraud Detection competition on Kaggle.
Sign in and accept the competition rules for your intended use before downloading.
Do not substitute a repackaged dataset with uncertain provenance.

Extract the official files into ignored `data/raw/ieee_cis/`. Keep the original
download. Do not commit the source or derived outputs. Run from the repository root:

```powershell
uv run python scripts/profile_ieee_cis.py --raw data/raw/ieee_cis --output artifacts/ieee_cis/run-001 --approved-use "Reference to your accepted terms and approved purpose"
```

Use a new output directory for each run. The saved program streams the training CSVs,
uses a temporary disk-backed key index, validates unique keys, binary labels and finite
nonnegative elapsed times, checks identity references, and records SHA-256 checksums.
Outputs are `eda.json`, `EDA.md`, and `split_membership.csv`.
The report includes per-column blank counts, fraud rates by partition, and identity
coverage. It exposes no raw feature values. Split membership contains source identifiers
and belongs in private data storage, never Git.

The default split requests 80% training by chronological row order. All rows at the
boundary time go to validation, so actual proportions may differ. Empty partitions fail.
Unmatched transactions remain in the split. Identity rows never multiply transaction rows.
This prepares partition membership only; it does not yet join feature tables, impute,
encode, train, or register a model. Fit future transforms only on the training partition.
Competition test tables remain untouched. No calendar date is inferred from TransactionDT.

Tests use explicitly synthetic records. Real EDA has not run until official files are
available. Synthetic test success does not establish dataset quality or model performance.

## Private S3 upload procedure

Upload the approved raw files, checksums, and outputs only to the project's private S3
location after verifying the account, region, access controls, retention, and budget.
Record each object version and checksum in an ingestion manifest. No bucket or upload
is created by this local program. Run analysis locally to avoid cloud compute spending.
S3 storage can still consume credits; the AWS budget is a monitor, not a spending cutoff.

Full feature preprocessing, training/evaluation, saved model export, LangGraph, MCP,
retrieval, and application deployment remain Target (not built yet).

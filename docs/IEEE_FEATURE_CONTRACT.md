# IEEE-CIS v3 feature builder

Implemented October 13, 2026 in src/risk_platform/ieee_features.py.

The builder accepts explicit numeric transaction and identity projections, not an
unrestricted CSV row. It requires every versioned numeric transaction column and a
nonnegative integer TransactionID. When identity exists, all numeric identity columns
and the matching integer key are required. An absent identity row is represented by
None. Column values may be finite numbers or bounded numeric CSV strings; None and
an empty string represent missing values. Booleans, nonfinite values, float32 overflow,
reserved-sentinel collisions, unexpected keys and incomplete projections are rejected.

Outputs use schema ieee-numeric-400-floatmin-missing-v1 in the exact 400-column order
of the v3 manifest. Float32 rounding and the reserved missing sentinel match the ONNX
wrapper. Transaction identifiers, time and target labels never become model inputs.

## Verified evidence

- Eleven synthetic tests passed: feature order, absent identity, invalid values,
  blank encoding, identity mismatch, label rejection and missing-column rejection.
- All ten source-derived golden input vectors matched the saved v3 requests exactly.
- Static feature ordering matched the private model manifest exactly.
- Ruff lint/format and source security checks passed.

The source-derived check selected the same ten evenly spaced audit rows as the
packaging script and joined train_identity.csv by TransactionID. Its aggregate receipt
is saved locally in model-v3/feature-verification.json; raw payloads remain private.

## Integration limits

This is an importable preprocessing component, not a newly deployed endpoint.
A caller must explicitly select the allowed numeric columns from raw records;
passing a complete row with label/time/categorical columns fails closed. It must also
validate duplicate/orphan records and establish that identity information was available
at the transaction's event time. IEEE-CIS alone does not prove online availability.

Next integrate the builder with database-backed replay and existing idempotent case
and score endpoints. Do not persist raw feature maps in score rows or replace the
verified baseline automatically. No AWS resources were created by this work.

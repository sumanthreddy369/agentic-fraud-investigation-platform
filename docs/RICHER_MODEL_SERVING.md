# Richer model export and API qualification

Verified October 13, 2026, locally. No cloud deployment or production approval implied.

| Check | Result |
| --- | --- |
| Histogram converter compatibility | Synthetic missing-branch parity passed |
| Python versus native ONNX | 118,108 audit rows; maximum absolute error 3.36704324e-07 |
| Finite missing-value wrapper versus native ONNX | 118,108 rows; maximum error 0 |
| Protected FastAPI golden scores | 10 passed; maximum error 0 |
| Authentication and schema checks | Unauthorized request and incorrect schema rejected |
| Adapter and export tests | 19 passed, 1 optional test skipped |
| Sequential in-process latency | 60 measured requests after 10 warmups; median 3.64 ms, p95 6.06 ms, max 9.09 ms |

Latency is a laptop ASGI sample, not concurrent load, network, database or AWS latency.
All 70 warmup/measured requests additionally checked prediction parity. Lint and
formatting passed. Existing runtime guardrails and default deployment were unchanged.

## Export repair

The installed skl2onnx histogram converter supplies boolean missing-direction flags
where the ONNX tree schema requires integers. A narrow custom converter delegates
all conversion to skl2onnx and converts only nodes_missing_value_tracks_true values
to integers. Installed packages were not modified. Missing-branch behavior is tested.
The converter relies on a library implementation function; dependency upgrades must
rerun parity tests before promoting any artifact.

## Versioned input contract

Candidate: ieee-hgb400-raw-v3. Schema: ieee-numeric-400-floatmin-missing-v1.
All 400 feature names must match the private manifest exactly. Inputs are float32
numeric values. Missing entries use the reserved value -3.4028234663852886e+38;
the ONNX graph converts this value to NaN internally before tree inference. Observed
audit values were checked for sentinel collisions. Integrations must reserve this
value and reject collisions; it is not a valid business measurement.

This preserves the API rejection of null/non-numeric model features without weakening
its shared contract. The caller still owns the documented identity join and ordered
feature construction; this is not yet an end-to-end raw-transaction preprocessing API.
The exported model is uncalibrated; calibration comparisons are documented separately.

## Reproduce

Run from the repository root with the approved dataset and earlier analysis manifest:

```powershell
$env:OMP_NUM_THREADS='2'
uv run --extra training --extra onnx-cpu python scripts/check_richer_export.py
uv run --extra training --extra onnx-cpu python scripts/package_richer_model.py
uv run python scripts/verify_model_api.py --model-dir artifacts/ieee_cis/model-v3
uv run python scripts/benchmark_richer_api.py
```

Outputs must not already exist. Model and manifest, private golden payloads and
verification JSON stay under ignored artifacts/ieee_cis/model-v3. The native graph
and parity results are under richer-export-check-v2. A failed conversion is recorded
as exported=false and packaging refuses it. No binary or raw payload belongs in Git.

## Next gates

Validate event-time availability and preprocessing, capture a concurrent HTTP/load
benchmark, package the candidate for containers, then run the costed AWS assessment
with screenshots and teardown. Previously examined audit data remains retrospective.
The existing 15-feature baseline has not been replaced or automatically promoted.

# Database-backed historical replay

Verified locally on October 13, 2026 using PostgreSQL 17, Docker, the guarded
FastAPI service and `ieee-hgb400-raw-v3`. This is historical portfolio replay,
not a live bank feed or an AWS deployment.

| Check | Observed result |
| --- | --- |
| Golden model predictions | 10/10 within 0.00001 absolute probability tolerance |
| Initial persisted records | 10 cases and 10 scores |
| Replay after API container restart | 10/10 reused original case and score IDs |
| Duplicate score rows | None; each case still had one score |
| Changed features with an existing replay key | HTTP 409; rejected |
| Database-backed readiness | Passed before and after restart |
| Raw features in score responses | Absent |
| Disposable containers and network | Removed after verification |
| Repository regression suite | 152 passed, 4 skipped |
| Ruff lint and formatting | Passed |

The four skipped tests require optional environments; this is not a claim that
every PostgreSQL trigger test ran. The separate Docker exercise above did execute
against PostgreSQL. Golden fixtures use synthetic source IDs and private real
feature vectors; payloads and the model are excluded from Git.

## Reproduce

Run `python scripts/verify_database_replay.py` in the locked environment with
Docker Desktop running, the existing `risk-platform:ieee-v1` image, and private
`artifacts/ieee_cis/model-v3/{manifest.json,model.onnx,golden.json}` present.
The script uses loopback-only HTTP, randomly generated temporary credentials,
a memory-backed database and a dedicated Docker network. It leaves unrelated
containers untouched. A private JSON receipt is written beside the model.

`scripts/replay_ieee.py` validates features and checks the advertised model version
before writes. Stable keys bind the source namespace, source transaction ID and
model version. The existing service binds those keys to request hashes. A completed
case followed by an interrupted score request can be replayed using the same keys.
No automatic retry or background worker is introduced.

Inventory preflight is not an atomic model-version pin: deployments must keep the
model fixed during replay. A post-score version check also fails on mismatch;
an unexpectedly scored record would require investigation, not deletion of its
append-only provenance. The HTTP calls are separate transactions. A durable queue,
crash-between-request test, multi-replica PostgreSQL contention, and cloud recovery
remain additional acceptance work.

The first restart exercise exposed changing Docker ephemeral host ports. The
harness now rediscovers the port and bounds health-check timeouts. The final
exercise was rerun successfully after this correction and model preflight addition.

# Model scoring through investigation and review

The local demonstration exercises the existing `ieee-hgb400-raw-v3` ONNX model through
the authenticated case API, bounded LangGraph workflow, review resource and audit history.
The model and its original qualification artifacts are preserved.

## Run

From the repository root, with an existing private model folder containing `manifest.json`,
`model.onnx` and `golden.json`:

```powershell
uv sync --frozen --python 3.11 --extra onnx-cpu --extra agents
uv run python scripts/demo_model_investigation.py --model-dir artifacts/ieee_cis/model-v3
```

Each execution creates a separate ignored directory under `artifacts/model-investigation-demo/`.
The directory contains the local SQLite database and aggregate `results.json`.
The demonstration prints no features or authentication tokens and calls no external provider.
It uses in-process ASGI transport; no HTTP server is exposed and no AWS resources are created.

The investigator instance creates cases, scores golden inputs, starts investigations and
checks that investigator review attempts are denied. A separate reviewer instance uses a
different generated token and the server-configured reviewer role to record scripted
`request_changes` decisions. A third application instance reopens the same database and
checks completion replay, persisted decisions and the expected audit sequence.

This role exercise is a test harness, not an independent human assessment or a multi-user
identity system. The application keeps the same owner identity throughout. OIDC and reviewer
assignment remain **Target (not built yet)**.

## Results — October 23, 2026

| Check | Measured result |
| --- | --- |
| Existing model golden predictions | 10 / 10 matched, maximum absolute difference 0.0 |
| Investigation completion records | 10 |
| Scripted reviewer decisions | 10 |
| Investigator review attempts rejected | 10 / 10 |
| Same-input completed runs replayed after application restart | 10 / 10 |
| Expected audit events | 40 |
| Packet disposition | All `insufficient_evidence` |
| Case status | All remained `open` |
| External provider calls / cloud resources created | 0 / 0 |

The exact match above compares these 10 fixtures with their saved expected probabilities;
it does not replace the separate full-audit Python-to-ONNX comparison. The selected model's
artifact SHA-256 is `fe9bbf2f72aaf8862389ceb8d9e7245f3f3824847c6f4f5dea1a7a9ee42bd0d8`.
The focused API/workflow/retrieval/policy regression suite also passed all 40 tests.

SQLite here demonstrates application persistence and replay. PostgreSQL append-only triggers
are covered by the separate database regression suite described in [the API guide](INVESTIGATION_API.md).
No new throughput, investigator time saving, AWS deployment or independent fraud decisions
are inferred from this run.

## Container preparation

The Dockerfile supports an explicit build option for the optional investigation dependencies:

```powershell
docker build --build-arg INSTALL_AGENTS=true -t risk-platform:investigations .
```

The default `INSTALL_AGENTS=false` retains the serving-only dependency set. Other values fail
the build. Installing dependencies does not enable execution: the runtime must explicitly set
`RISK_INVESTIGATIONS_ENABLED=true`, apply migrations and configure authentication.
The image still runs as UID/GID 10001, and model artifacts remain outside the build context.

The investigation-enabled image build has not been executed because Docker Desktop's Linux
engine was unavailable during this assessment. Build and container runtime qualification are
the next checks before using that image in any AWS assessment.

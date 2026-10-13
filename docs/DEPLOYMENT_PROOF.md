# Existing-model deployment proof

Status as of October 13, 2026: the local image `risk-platform:ieee-v1` built
successfully and served ten matching golden predictions over loopback HTTP from a
temporary non-root container with a read-only model mount. The container was stopped
after verification. Kubernetes deployment, recovery, scaling, and Terraform apply
remain unproven. No local Kubernetes context is configured.

The current FastAPI scoring endpoint is `POST /v1/models/{domain}/score` with bearer
authentication. Reuse this boundary; do not add an unauthenticated parallel service.
The supplied model must match a supported domain and include its preprocessing
contract, SHA-256, ONNX manifest, and golden input/output examples. A dataset or
generated test graph is not evidence of an existing trained fraud model.

The user subsequently approved training a new baseline. The resulting real trained
ONNX artifact and its limitations are documented in [BASELINE_MODEL.md](BASELINE_MODEL.md).
This does not satisfy a claim that an older portfolio model was recovered.

## Saved deployment components

- `Dockerfile`: locked CPU inference dependencies, non-root process, explicit startup.
- `.dockerignore`: allowlist excludes datasets, model binaries, secrets, and Git state.
- `infra/local/main.tf`: local Docker Desktop Kubernetes namespace, API deployment,
  and internal service with resource bounds, probes, read-only model mount, and
  disabled service-account token mounting. This is an unvalidated draft.

Required before applying: running local Kubernetes, built image, `risk-runtime`
Secret, `risk-models` PVC with verified artifact, and reachable migrated PostgreSQL.
Namespace creation precedes these prerequisites. Database and model storage
provisioning are not yet implemented in this module. Secrets must not enter Git or
Terraform variables/state. The manifest must reference the model under `/models`.

The readiness endpoint checks database/schema readiness, not successful model scoring.
Deployment acceptance must additionally verify authenticated model availability and
golden predictions. Rate limits and scoring circuits remain per-process, so replica
scaling multiplies aggregate capacity; this is a local single-operator exercise.

## Required proof, captured as actual results

| Claim | Acceptance evidence |
| --- | --- |
| Existing model | Provenance, manifest hash, preprocessing parity, and golden score comparison |
| Clean deployment | New isolated environment, migrations, healthy replicas, authenticated prediction |
| Recovery | Delete one disposable API pod; new UID becomes ready and predictions match |
| Scaling | Apply replicas 1 then 3, verify all ready and identical golden predictions per replica |
| Reproducibility | Commit provider lock, capture no-change Terraform plan, rebuild isolated environment and repeat smoke test |
| Cost cleanup | Remove only disposable test workloads after evidence capture; retain dataset and model |

Keep test results and screenshots under ignored `artifacts/` until reviewed for
publication. Do not expose the local bearer-token service with an ingress or public
LoadBalancer. Shared/cloud deployment needs the project's stronger identity design.

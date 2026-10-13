# Local Kubernetes deployment proof

Verified October 13, 2026. The disposable kind cluster and Terraform resources were
removed after the proof. No AWS compute was created for this exercise.

## Results

| Check | Observed result |
| --- | --- |
| Clean deployment | Terraform created namespace, PostgreSQL deployment/service, migration job, API deployment/service; readiness passed |
| Fraud prediction | 10 authenticated golden predictions matched the calibrated RF reference |
| Recovery | Deleted API pod was replaced with a different UID; 10 predictions passed again |
| Scaling | Terraform changed API replicas from 1 to 3; 10 predictions passed on each individual replica |
| No drift | Terraform plan with 3 replicas returned detailed exit code 0 |
| Rebuild | Destroyed all six Terraform resources, recreated namespace/secrets/workloads, and passed 10 predictions again |
| Cleanup | Terraform destroy succeeded; kind reported deletion of risk-proof-control-plane |

Total: 60 golden HTTP predictions across initial deployment, recovery, three
replicas, and rebuild. Maximum absolute prediction error was 8.1633e-08, below
1e-05 tolerance. Every tested pod also rejected an unauthenticated scoring request.
Database/schema readiness returned ready. Model identity: ieee-rf15-sigmoid-v2.
See [model comparison and limitations](FULL_EDA_COMPARISON.md).

## Scope

This proves local single-node workload deployment, API pod recovery, manual replica
scaling, and Terraform workload rebuild. It does not prove node-failure tolerance,
autoscaling, throughput improvement, persistent database recovery, production high
availability, or AWS deployment. PostgreSQL uses disposable emptyDir storage.
The kind cluster is bootstrapped separately, not managed by Terraform.

The API uses non-root execution, a read-only root filesystem and model mount,
dropped capabilities, resource bounds, readiness/liveness probes, and an internal
ClusterIP service. Smoke checks use loopback-only port forwarding. No public ingress
or load balancer was created. Credentials are generated outside Terraform state;
the local token file is ignored and only useful while the disposable cluster exists.
Rate limits and scoring circuits are per process, not shared across replicas.

## Reproduce on this Windows workstation

Prerequisites: running Docker Desktop, Docker CLI and kubectl on PATH, kind 0.33.0
at .test-runtime/tools/kind.exe, Terraform 1.14.9 at
.test-runtime/tools/terraform.exe, and a verified model-v2 directory. The committed
provider lock selects hashicorp/kubernetes 3.3.0. The run used kindest/node:v1.37.0,
postgres:17, and the locally built risk-platform:ieee-v1 image. Tags are not immutable
pins; bit-for-bit image rebuild reproducibility remains future work.

Run from the repository root. These resources and database must remain disposable.
Do not reuse this workflow for an existing production namespace or database.

```powershell
uv sync --frozen --extra training --extra onnx-cpu
# Follow FULL_EDA_COMPARISON.md to prepare the private model artifacts first.
docker build -t risk-platform:ieee-v1 .
$mount = (Join-Path $PWD 'artifacts/ieee_cis').Replace('\', '/')
@"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraMounts:
  - hostPath: $mount
    containerPath: /risk-models
    readOnly: true
"@ | Set-Content .test-runtime/kind-risk.yaml
.\.test-runtime/tools/kind.exe create cluster --name risk-proof --image kindest/node:v1.37.0 --config .test-runtime/kind-risk.yaml --kubeconfig .test-runtime/risk-kubeconfig
.\.test-runtime/tools/kind.exe load docker-image risk-platform:ieee-v1 --name risk-proof
$kubeconfig = (Join-Path $PWD '.test-runtime/risk-kubeconfig').Replace('\', '/')
$vars = @('-var=image=risk-platform:ieee-v1', "-var=kubeconfig=$kubeconfig")
.\.test-runtime/tools/terraform.exe '-chdir=infra/local' init -lockfile=readonly
.\.test-runtime/tools/terraform.exe '-chdir=infra/local' validate
# Targeting is used only to bootstrap the namespace before external secrets.
.\.test-runtime/tools/terraform.exe '-chdir=infra/local' apply '-target=kubernetes_namespace_v1.risk' @vars
uv run python scripts/bootstrap_local_secrets.py
.\.test-runtime/tools/terraform.exe '-chdir=infra/local' apply @vars
uv run python scripts/prove_local_cluster.py
# This proof script leaves 3 replicas. Save its evidence, then tear down.
.\.test-runtime/tools/terraform.exe '-chdir=infra/local' destroy '-var=replicas=3' @vars
# Repeat namespace bootstrap, secret generation and full apply to test rebuild.
# Finally destroy the rebuilt workloads before deleting the cluster:
.\.test-runtime/tools/kind.exe delete cluster --name risk-proof --kubeconfig .test-runtime/risk-kubeconfig
```

The proof script deliberately hardcodes the isolated context and Windows tool
locations. Adjust tool locations when porting it. A rebuilt database starts empty;
bootstrap_local_secrets.py generates new credentials and should only be run against
a fresh namespace before starting PostgreSQL.

## Evidence retained locally

Ignored artifacts/ieee_cis/cluster-proof contains results.json, recreate-result.json,
scaling.log, no-drift-plan.log, both destroy logs, and rebuild logs. These contain
execution evidence; screenshots and diagrams alone are not acceptance tests.
Dataset/model binaries, raw predictions, kubeconfig, and credentials are excluded
from Git. Aggregate figures and this report are published for portfolio review.

## Automated checks

After the changes: 133 tests passed, 4 skipped in the default suite. Optional
PostgreSQL/OpenVINO coverage must not be inferred from that default run. Ruff lint
and formatting passed. New analysis tests cover probability-bin endpoints,
undefined metrics for single-class groups, and confusion-matrix rates.

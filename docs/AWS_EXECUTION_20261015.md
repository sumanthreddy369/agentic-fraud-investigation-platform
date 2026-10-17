# AWS deployment attempt — October 15, 2026

## Verified live outcome

At 22:46 UTC, AWS reported the following for the disposable portfolio environment:

| Component | Observed result |
| --- | --- |
| EKS control plane | ACTIVE, Kubernetes 1.35 |
| Private Kubernetes endpoint | Enabled |
| Public Kubernetes endpoint | Disabled |
| Managed node group | CREATE_FAILED |
| Desired worker count | 2; this is a configuration value, not running capacity |
| Failure category | AsgInstanceLaunchFailures |
| Launch rejection | The selected m6i.large type was not eligible for this account's Free Tier plan |
| Application deployment | Not performed |
| AWS prediction, recovery and scaling tests | Not performed |

The earlier Terraform apply created infrastructure, but did not establish a usable
application cluster. Credits and an available regional instance offering did not
prove that this account could launch the selected instance type. A future preflight
must check account-plan restrictions and instance eligibility before creating EKS
or a NAT gateway. Do not upgrade the account automatically.

The attempted model upload failed when CloudShell suspended. No successful model
transfer or image push was verified. The private operator-network permission
expansion was declined and was not attached.

## Recovery and cleanup

Cleanup was verified at 23:27 UTC (6:27 PM CDT) on October 15. Terraform reported
0 added, 0 changed and 25 destroyed; its subsequent state list was empty.
The failed node group had not been recorded by the interrupted apply, so it was
imported before generating and reviewing the final destroy plan. The abandoned
state lock was released only after checking that no Terraform process remained.

| Post-cleanup check | Result |
| --- | --- |
| Matching EKS cluster | Absent |
| Project-tagged EC2 instances | Empty result |
| Project-tagged EBS volumes | 0 |
| Project-tagged allocated public IPs | 0 |
| Demo NAT gateway | deleted |
| Matching ECR repository | Absent |
| Matching EKS log groups | 0 |
| Terraform managed resources | Empty state list |

The original S3 dataset, state history, local models and existing operator identity
were outside the destroy plan and preserved. This is a demo-scoped cleanup, not an
account-wide zero-charge certification. Retained storage and delayed billing can
still appear. Raw console screenshots and Terraform state remain private.

## Prevention changes

Worker instance type is now an explicit required Terraform variable. A new
read-only `scripts/check_aws_worker_eligibility.py` checks Free Tier metadata and
x86_64 compatibility before provisioning. Five focused tests pass; together with
the infrastructure evidence tests, seven pass. Ruff and Terraform formatting pass,
and Terraform configuration validation succeeds. This gate does not replace quota,
capacity, account-plan and cost checks.

## Remaining demonstration gates

1. Completed: verify deletion of this failed disposable environment.
2. Select account-permitted capacity and validate the private operator access path.
3. Complete the model transfer and container build before starting another timed demo.
4. Deploy the API and persistence, then measure predictions, recovery and scaling.
5. Capture a no-change Terraform plan and verify final teardown.

Local model and Docker results remain valid within their documented scope; they
must not be relabeled as AWS application results. Agents and external model-provider
integrations remain targets until executable implementation and tests exist.

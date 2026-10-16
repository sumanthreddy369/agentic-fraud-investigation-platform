# Temporary AWS EKS assessment — first attempt cleaned up

Current status: the October 15 apply created a private control plane, but worker
creation failed. All 25 tracked resources were subsequently destroyed and cleanup
was verified. See [the execution report](../../docs/AWS_EXECUTION_20261015.md).
The application has not been deployed on AWS. Dated preflight notes below are
historical; lifecycle and agent services remain separate work.

## Proposed resources

- A dedicated VPC, two private subnets and one public subnet for outbound NAT.
- One NAT gateway and one charged public IPv4 address; nodes have no public IPs.
- Private EKS API, standard-support Kubernetes version selected at deployment.
- Two nodes of an explicitly reviewed x86_64 instance type, each with a 30 GB encrypted gp3 disk.
- EKS cluster/node IAM roles, an explicitly supplied operator role access entry.
- Immutable-tag ECR repository and one-day control-plane log retention.
- Operator security group for a CloudShell VPC environment, with cluster API
  access limited to HTTPS from that group. No public application load balancer.

The current prepared configuration uses node-role CNI permissions. Separate CNI
pod identity is a hardening follow-up. IMDSv2 is required and hop limit is one.
This configuration is a disposable portfolio exercise, not a highly available
production platform: one NAT gateway is a shared dependency and cross-AZ egress
may incur transfer charges. ExpiresAt is an inventory tag, NOT an automatic stop.

## Preflight facts and remaining gates

Console/CloudShell inspection on October 14 showed estimated credits of $158.92,
16 standard-instance vCPUs allowed, no EKS clusters in us-east-1, and one stopped
credit-test EC2 instance with an 8 GB attached disk. This is a regional inventory,
not proof that the whole account has no other billable resources.
EKS reported 1.34–1.37 in STANDARD_SUPPORT. No suitable existing operator IAM role
was found: only service-linked and Lambda test roles were listed.

Prepared access bootstrap: `scripts/prepare_aws_operator.py` writes two private
JSON documents for `risk-portfolio-demo-operator`. The trust policy requires an
explicitly approved same-account non-root IAM user or role (PrincipalArn
condition). Its IAM permission is only `eks:DescribeCluster` on the named demo
cluster in us-east-1. Create with a maximum session duration of 3600 seconds only
after action-time approval. It does not grant general AWS administration or create
access keys. The separate Terraform EKS access policy grants administration of the
demo cluster and must be included in the subsequent deployment/access review.

Verification finding: the initially approved root-only trust role was created,
but STS rejected its use because root accounts cannot assume roles. The role has
no working operator session and no EKS cluster access yet. The generator now
rejects root principals. Changing the live trust to a named non-root identity
requires separate approval; no broad account-wide trust was substituted.

After the user approved the correction, `risk-portfolio-user` was created with
AWSCloudShellFullAccess and an inline permission to assume only the demo operator
role. The role trust update names this specific user. Console password/MFA setup
is a user handoff; no access keys were created. A successful non-root operator
session remains to be verified before deployment. Four generator tests pass,
including rejection of root, foreign-account and wildcard principals.

Before apply: review the complete saved plan, provide an approved operator role,
check Free Tier plan/service eligibility, confirm current regional rates, set a
short teardown window and verify private administration connectivity. Do not
enable public cluster access to work around connectivity. Browser-driven creation
of the IAM permissions requires action-time user confirmation.

EKS standard support is listed at $0.10/cluster-hour on the
[AWS pricing page](https://aws.amazon.com/eks/pricing/). Node compute, NAT hourly
and data processing, IPv4, EBS, registry storage, logs and transfer are additional.
Use the [VPC](https://aws.amazon.com/vpc/pricing/),
[EC2](https://aws.amazon.com/ec2/pricing/on-demand/) and
[EBS](https://aws.amazon.com/ebs/pricing/) regional rates for the final estimate.
No total deployment estimate has yet been approved or guaranteed.

### October 15 preflight

The account API reports an ACTIVE FREE plan and $158.91 remaining credits.
Read-back of the operator role confirms its trust condition is restricted to
`risk-portfolio-user`, with a 3600-second maximum session. The initial session was
root. After the user signed in as `risk-portfolio-user`, STS verified that identity
and successfully assumed `risk-portfolio-demo-operator` for 900 seconds. Only the
assumed role ARN was printed; credentials were not displayed or saved. Evidence:
`artifacts/aws-preflight/operator-success-20261015.jpg` (private, excluded from Git).
The role still only permits describing the named cluster; this does not prove
provisioning permissions or Kubernetes administration.

Terraform 1.14.9 was downloaded from HashiCorp in CloudShell and its ZIP checksum
verified. The large AWS provider exhausted CloudShell's 1 GB persistent home
storage; use a dedicated `/tmp` working directory and `TF_DATA_DIR` for planning.
Temporary storage is not an acceptable sole location for applied infrastructure
state. Before any apply, establish protected persistent state and recovery.
The provider lock must include Linux and Windows package hashes; generate them
with `terraform providers lock -platform=linux_amd64 -platform=windows_amd64`.

After initializing in temporary storage with the Linux checksum recorded, the
account-backed plan succeeded: **28 to add, 0 to change, 0 to destroy**, using
Kubernetes 1.35. No apply ran. The private screenshot is retained locally under
`artifacts/aws-preflight/terraform-plan-20261015.jpg`. Regenerate the plan with a
fresh teardown deadline after the remaining access, cost and state-storage gates
pass; the current review plan is not authorization to deploy.

## Execution and evidence

For durable state, the prepared `backend.tf.example` and `backend.hcl.example`
select a dedicated state key in the existing private project bucket, with S3
native locking and encryption. Replace the bucket placeholder in a private local
copy. These examples have not been initialized against S3. First recheck bucket
versioning, encryption, public-access block and access to
the exact prefix. Copy the Terraform example to `backend.tf`, then initialize with
`terraform init -backend-config=<private-backend-config>`. Do not use `/tmp` as the sole
state store for an apply. Preserve the bucket and its original dataset during demo
teardown. State can contain sensitive values; never publish it or its backups.

Provisioning requires an administrator/deployment session. The successfully
verified operator role deliberately cannot create the AWS resources. The previous
administrator session expired after switching to the IAM operator; authenticate
the provisioning identity before attempting any apply. The user approved the
28-resource plan, including its cluster/node roles and operator cluster-admin
association, after successful operator verification. This approval does not imply
that an apply has run or that the remaining preflight gates passed.

1. Initialize from the committed lock file with short-lived AWS authentication.
2. Supply account_id, operator_role_arn, kubernetes_version, worker_instance_type and expires_at in an
   ignored variables file. State and saved plans stay private and protected.
3. Run `terraform plan -out=<private-plan-path>` and review all changes.
4. Apply only after the access and cost gates above pass. Establish CloudShell VPC
   access using the private subnet and operator security-group outputs.
5. Deploy version-pinned model/API, migrations and database. Capture predictions,
   restart recovery, scaling and a subsequent no-change Terraform plan.
6. Export only sanitized evidence. Delete disposable workloads/PVCs and any
   load-balancers they created before infrastructure teardown.
7. Remove the CloudShell VPC environment and its ENIs before destroying the VPC.
   ECR force_delete is false: verify/export required evidence and explicitly remove
   only demo images before destroying the repository.
8. Destroy infrastructure; confirm no tagged nodes, disks, NAT, EIPs, clusters,
   repositories or logs remain. Recheck billing later for delayed usage.

Preserve original S3 datasets, baseline models and unrelated resources. A new
demonstration does not authorize deleting resources outside its reviewed inventory.

## October 15 execution correction

The first AWS apply reached an ACTIVE private EKS control plane, but worker creation
failed because m6i.large was ineligible under the account Free Tier plan. See
[the execution report](../../docs/AWS_EXECUTION_20261015.md). Earlier no-apply
statements above describe the preflight history and are superseded by that report.

Worker type is now a required `worker_instance_type` variable, with no automatic
fallback. Before another plan, run:

```powershell
uv run python scripts/check_aws_worker_eligibility.py --instance-type <reviewed-type>
```

This read-only gate checks EC2 eligibility metadata, x86_64 compatibility, and a
default capacity floor of 2 vCPUs and 8192 MiB per worker. Explicit positive
`--min-vcpus` and `--min-memory-mib` overrides support a reviewed sizing change.
The floor is a conservative demo screening rule, not a measured scheduling guarantee.
It does not prove account launch permission, quotas, AZ capacity, workload fit,
or zero cost. Check those separately, plus private operator connectivity, model
transfer and image availability, before incurring control-plane/NAT costs. An
ExpiresAt tag is not an automatic shutdown mechanism.

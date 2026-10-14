# Temporary AWS EKS assessment — not deployed

Prepared October 14, 2026. This directory is infrastructure code, not deployment
evidence. No Terraform apply has run. Application deployment and lifecycle/agent
services remain separate work.

## Proposed resources

- A dedicated VPC, two private subnets and one public subnet for outbound NAT.
- One NAT gateway and one charged public IPv4 address; nodes have no public IPs.
- Private EKS API, standard-support Kubernetes version selected at deployment.
- Two m6i.large nodes (four vCPUs total), each with a 30 GB encrypted gp3 disk.
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
JSON documents for `risk-portfolio-demo-operator`. The trust policy permits only
the current account root principal to assume the role (explicit PrincipalArn
condition). Its IAM permission is only `eks:DescribeCluster` on the named demo
cluster in us-east-1. Create with a maximum session duration of 3600 seconds only
after action-time approval. It does not grant general AWS administration or create
access keys. The separate Terraform EKS access policy grants administration of the
demo cluster and must be included in the subsequent deployment/access review.

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

## Execution and evidence

1. Initialize from the committed lock file with short-lived AWS authentication.
2. Supply account_id, operator_role_arn, kubernetes_version and expires_at in an
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

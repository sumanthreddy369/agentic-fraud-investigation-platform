# AWS preparation — October 17, 2026

The selected ONNX model bundle was transferred to private S3 storage. A read-back
of the exact object version confirmed 20,429 bytes, AES256 server-side encryption,
and a SHA-256 checksum matching the local archive. Bucket versioning is enabled
and all four S3 public-access blocking settings are enabled.

The archive contains only `model.onnx` and `manifest.json` for
`ieee-hgb400-raw-v3`. The private transfer record retains the bucket, object key,
and version ID. Dataset rows, credentials, and model binaries are excluded from Git.

| Check | Observation |
| --- | --- |
| Candidate worker | m7i-flex.large |
| EC2 eligibility metadata | FreeTierEligible: true |
| Architecture | x86_64 |
| Capacity per worker | 2 vCPUs, 8192 MiB |
| Regional offerings | us-east-1a, 1b, 1c, 1d, 1f |
| Standard On-Demand instance quota | 16 vCPUs; this is the quota, not unused capacity |
| EKS clusters in us-east-1 | Empty list |
| Model transfer | S3 upload and exact-version metadata read-back completed |

Eligibility and offerings do not guarantee launch permission or available capacity.
The transfer does not establish a running prediction service. No EKS cluster, worker,
or NAT gateway was created during these checks. S3 storage remains billable.

## Next deployment steps

Resolve private operator connectivity, build and test the container image, review
the revised Terraform plan and current costs, then run the timed AWS assessment.
The earlier CloudShell network policy references deleted resources and must not be
reused. Keep the Kubernetes API private and remove temporary access during cleanup.

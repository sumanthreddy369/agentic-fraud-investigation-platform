# AWS access check — October 18, 2026

The private CloudShell environment did not reach a usable terminal. Its error
panel reports that the operator user lacks `ec2:DescribeSubnets`. The temporary
network policy remains attached, but every grant expired at October 18 00:30 UTC.
The error alone does not establish the cause or timing of the original failure.

An administrator read-back confirmed policy version v1 and one attachment. Both
demo private subnets remain available in the expected VPC. An expiry-only renewal
was prepared and passed IAM Access Analyzer with no findings; preparation is not
an applied permission change. The network scope and principal are unchanged.

## Container preparation

Release `c0f07c4` built successfully in standard AWS CloudShell on October 17.
The resulting Docker image ID was
`sha256:62a64a043577d8705d91c6e460bfbad1b7fc25f00be00535419721cce25bcaef`.
A loopback-only smoke container returned HTTP 200 with `{"status":"alive"}` from
`/health/live`, ran as UID/GID `10001:10001`, and was removed after the check.
The subsequent container-name query returned no matching containers.

This proves image build and process liveness in CloudShell. It does not prove
database readiness, model scoring, EKS deployment, recovery or scaling. The image
has not been published to ECR, and CloudShell temporary storage is not a durable
release registry.

Raw AWS screenshots are saved locally under `artifacts/aws-preflight/` and are
excluded from Git because they include account and infrastructure identifiers.

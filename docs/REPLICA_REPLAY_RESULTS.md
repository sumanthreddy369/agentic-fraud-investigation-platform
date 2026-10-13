# Three-replica bounded replay

Executed October 13, 2026 against the richer ieee-hgb400-raw-v3 model.

| Measurement | Result |
| --- | --- |
| Requests completed | 60 of 60 |
| Replicas | 3 local Docker containers |
| Requests per replica | 19 / 21 / 20 |
| Prediction error | 0 against golden references |
| Retries | 0 |
| Queue | At most 6 waiting items, plus a producer blocked on admission |
| In-flight calls | At most 1 per replica |
| Wall time | 1.99 seconds |
| Measured completion rate | 30.21 requests/second for this short run |
| HTTP p95 | 117.82 ms |
| Waiting/admission p95 | 283.91 ms |
| End-to-end p95 | 386.42 ms |
| Cleanup | All three temporary containers stopped and auto-removed |

The replay producer slows when its queue fills. Three dedicated workers each send
one request at a time to a specific replica; the model guardrails remain unchanged.
A failed worker cancels its sibling tasks through an asyncio TaskGroup. Failed
requests are not retried. Submission timestamps include producer admission waiting.
Percentiles are measured separately and should not be added together.

This demonstrates bounded local historical replay, not a production request queue,
Kubernetes load balancing, autoscaling or a sustained AWS throughput guarantee. Ten
private golden payloads were repeated six times, so this is not a representative
transaction distribution. Database readiness was not tested. All replicas share the
laptop Docker engine. Memory limits are 1 GiB and CPU limits are 2 per container.

The prior unqueued four-client test produced 22 HTTP 503 responses out of 40 requests.
This exercise changes both replica count and admission behavior; improvement cannot
be attributed to replicas alone. Queue persistence, redelivery/idempotency and crash
recovery remain necessary for an operational event pipeline. The process-local queue
would lose pending work if the replay process stopped.

## Reproduce

```powershell
uv run python scripts/verify_replica_replay.py
```

Requires Docker Desktop, the prior risk-platform:ieee-v1 image and private model-v3
artifacts. The script uses the documented Windows Docker path, random container names,
loopback ports and a read-only model mount. Credentials are generated in process and
not printed. Aggregate results remain under model-v3/replica-replay.json. Lint and
format checks passed; the actual integration run checked each prediction.

## Next cloud gates

Add a versioned raw-transaction feature builder, database-backed idempotent replay,
and Kubernetes service/load tests for this richer model. Use the resulting workload
and resource measurements in the AWS Terraform plan. Capture real AWS evidence and
verify teardown after the demonstration; this run created no AWS resources.

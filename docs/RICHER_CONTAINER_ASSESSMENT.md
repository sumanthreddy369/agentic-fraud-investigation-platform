# Richer-model container and concurrent HTTP assessment

Executed October 13, 2026. Local Docker loopback test; not an AWS benchmark.

| Measurement | Result |
| --- | --- |
| Sequential golden predictions | 10 passed, maximum error 0 |
| Concurrent requests / client workers | 40 / 4 |
| Successful predictions | 18; every successful response passed parity |
| HTTP 503 responses | 22; no hidden retries |
| Successful-response median | 199.69 ms |
| Successful-response p95 | 326.46 ms |
| Burst wall time | 1.99 seconds |
| Post-burst prediction | Passed |
| Cleanup | Temporary container stopped and automatically removed |

## Interpretation

This is a correctness and overload observation, not a throughput success claim.
The gateway deliberately allows one in-flight inference per domain per process.
The burst produced substantial 503 rejection, so this single replica does not meet
an assumption of four simultaneous successful scoring requests. Successful-response
latencies exclude rejected calls and must not be presented as overall latency SLOs.
The post-burst request proves service recovery for this small exercise only.

The image was reused from the earlier verified API build, with the new v3 model mounted
read-only. Image identity: `sha256:1eb16bc1ddc9813962c8a55482231547599180ae5ca97ac65ea3230db335a80c`. The process ran as the image's non-root
user, with a read-only root filesystem, dropped capabilities, no new privileges,
1 GiB memory limit and two CPUs. Only a random loopback host port was exposed.
Model: ieee-hgb400-raw-v3. Private feature payloads and binaries remain excluded from Git.

Database readiness was not tested. Results depend on this laptop and Docker VM;
they do not establish AWS latency, high availability, sustained load or service capacity.
The earlier in-process latency sample is a different test and cannot be directly
compared as a like-for-like performance regression.

## Next acceptance work

Measure the same workload through multiple replicas, preserve one-call-per-domain
bounds, and define explicit queue/backpressure behavior for historical replay.
Verify end-to-end preprocessing and database readiness with the richer model before
cloud rollout. Publish errors alongside throughput; do not bypass guardrails merely
to improve the success count. AWS deployment, monitoring and agents remain incomplete.

## Reproduce

```powershell
uv run python scripts/benchmark_model_container.py --docker "C:/Program Files/Docker/Docker/resources/bin/docker.exe" --model-dir artifacts/ieee_cis/model-v3
```

Requires Docker running, the existing risk-platform:ieee-v1 image and private v3
artifacts. The script stops its uniquely named container in a finally block.
Aggregate output is saved as model-v3/container-concurrency.json. Ruff lint and
format checks passed. This run created no AWS compute.

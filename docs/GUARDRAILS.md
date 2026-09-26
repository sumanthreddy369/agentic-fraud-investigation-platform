# Guardrails: implementation and showcase guide

This project demonstrates defense in depth for a fraud investigation service. There is no universal set of guardrails that makes a platform production-ready or compliant. The controls below address the current API and prepare bounded interfaces for future agents. They do not change or retrain the existing IEEE-CIS, Home Credit, or Elliptic models.

**Status legend:** Live = enforced by the current API; Policy = implemented and tested as an agent integration library, not yet connected to LangGraph/MCP/Azure; Deployment = infrastructure, identity, or workflow work still required.

## Live API controls

| Threat / failure | Control and default behavior | Evidence / limitation |
| --- | --- | --- |
| Anonymous access | Bearer authentication for all `/v1` routes; empty configuration denies access; constant-time byte comparison | Authentication tests. Health and optional documentation remain public on loopback. |
| Privilege escalation | Server-configured investigator, reviewer, and auditor permission sets; client role headers do not grant permissions | `test_read_only_roles_and_spoofed_role_header`. This is local role simulation, not enterprise user provisioning. |
| Other users' cases | Owner filters on reads, listings, audit retrieval and idempotency scope; inaccessible objects return 404 | Existing ownership tests. Multi-user OIDC and PostgreSQL RLS remain pending. |
| Cross-domain access | Server-configured allowed domains filter case/model APIs; empty set grants none | `test_domain_restriction_hides_existing_case_and_audit`. No inferred cross-dataset joins. |
| Accidental mass assignment | Pydantic rejects unknown fields, invalid domains, and malformed source identifiers | Existing API contract tests. |
| Huge / malformed payloads | 64 KiB actual body-byte limit, 16 KiB header limit, JSON-only write routes, compressed-body rejection, ambiguous framing rejection | Declared, understated and streamed body tests. Header bytes are checked after the HTTP server has parsed them; edge limits remain necessary. |
| Slow uploads / overload | 5-second body deadline, 20 concurrent requests per process, fail-fast capacity rejection | Slow-body and concurrent-request tests; sockets and upstream protection need gateway controls. |
| Request flooding | 120 requests/minute/peer, fixed windows, bounded 1,024-client map; spoofed forwarding headers ignored | Rate-limit tests. Process-local counters reset on restart; boundary bursts and NAT sharing are expected. Not a distributed quota or DDoS defense. |
| Host-header abuse | Explicit host allowlist; launcher does not trust forwarded client addresses | Untrusted-host test. No permissive CORS policy is configured. |
| Sensitive errors | Validation errors omit raw input/context; unexpected and database errors return generic details | Secret-marker test checks responses and platform logs. |
| Sensitive telemetry | Structured allowlisted JSON events include generated request ID, route template, status and duration; omit bodies, tokens, query strings and raw exception messages | Log-redaction test. Uvicorn access logging is disabled in the supported launcher. Centralized logging is pending. |
| Browser caching / embedding | `no-store`, `nosniff`, frame denial, no-referrer; API responses use restrictive CSP | Header tests, including denied requests. No HSTS is claimed over local HTTP. |
| Excessive list queries | Bounded case pagination, maximum offset, and bounded audit pages | Contract validation; use audit `limit`/`offset` to continue reading history. |
| Duplicate writes | Owner-scoped idempotency keys; conflicting payloads return 409; one transaction creates case and audit record | PostgreSQL test races six submissions and verifies a single case/audit event. |
| Audit modification | PostgreSQL trigger rejects UPDATE, DELETE and TRUNCATE | Real PostgreSQL tests. Database owners can disable triggers; separate runtime roles and an external immutable archive are still required. |
| Hung database work | Pool limits and connection, statement (5s), lock (1s), and idle-transaction (10s) timeouts | PostgreSQL verifies session timeout settings. Timeouts are not a guarantee that a disconnected caller's write did not commit; retry using the same idempotency key. |
| Missing model artifacts | All three models remain unavailable until their authoritative contracts/artifacts are recovered | Availability tests; no synthetic fallback scores. |
| Malformed model inputs/outputs | Bounded feature keys/count/strings, strict scalar values, finite probability in [0,1], domain/schema match, nonempty model/version/class metadata | Fake-adapter adversarial tests. Training-feature parity, calibration and drift cannot be verified without original models. |
| Slow / failing model | 5-second async timeout, one concurrent call/domain, circuit opens after three failures, 30-second cooldown then one recovery probe; no automatic scoring retries | Timeout/recovery tests. Async cancellation requires cooperative adapters; CPU-bound models need isolated worker processes. |
| Emergency containment | Configuration disables case writes or scoring; reads remain available; documentation can be disabled | Kill-switch tests. Environment changes require restart; distributed operational kill switches are pending. |

## Agent, retrieval and AI controls

Implemented in `agent_policy.py`, verified with synthetic tools. These controls become effective for real agents only when every tool and model-output path is routed through this boundary.

| Threat / failure | Policy enforced | Integration boundary |
| --- | --- | --- |
| Excessive agency / unknown tools | Deny by default; only explicitly registered `get_case_evidence`, `search_policy`, and `get_graph_neighborhood` tools can run | No shell, arbitrary SQL, arbitrary URL fetch, account block, payment, loan approval, or self-approval tool. |
| Tool argument injection | Typed bounded arguments reject extra fields; case, domain and identity come from trusted server context | Never construct this context from LLM-provided claims. Retrieval implementations must also apply authorization before searching. |
| Cross-case evidence leakage | Returned evidence must match authorized case, domain and owner; reject the entire batch on mismatch | Qdrant metadata filters are not yet integrated. |
| Runaway ReAct loops | Five tool calls/run, 30-second run budget, five-second tool deadline, no parallel tool calls, failed calls spend budget | Counters are in-memory. Durable distributed budgets and actual Azure token/cost accounting are pending. |
| Excessive evidence / poisoned IDs | Bounded excerpts and cumulative evidence counts; reject same-ID/different-content collisions | Ingestion signing, provenance checks, malware scanning, and source deletion propagation are pending. |
| Fabricated citations | Recommendations may reference only collected evidence IDs; duplicate/unknown citations are rejected | A valid citation establishes provenance, not entailment or truth. Semantic groundedness evaluation is still required. |
| Unsupported conclusions | Empty evidence only permits an `insufficient_evidence` recommendation | Fraud labels and risk scores remain outputs of verified models, not invented LLM probabilities. |
| Autonomous consequential action | Every accepted recommendation is a review packet with `requires_human_review=true`; no approval or action executor exists | This is not yet a durable analyst workflow. Add authenticated reviewer separation, evidence-version binding, expiry, replay protection and atomic decision transitions before enabling actions. |
| Unapproved cloud disclosure | External AI payload preparation disabled by default; opt-in still requires public classification AND explicit approval for every evidence item | No network request is made by this library. Restrict egress at infrastructure and Azure client boundaries during integration. |
| Obvious sensitive content | Additional email, SSN-like, card-like and credential-assignment screen denies marked snippets | Heuristic only; it misses formats/languages and can have false positives. It is not complete DLP, anonymization, PCI or privacy compliance. |
| Prompt injection in documents | Retrieved text is treated as untrusted evidence; it cannot grant tools, change case identity, or bypass a review packet | No claim to detect every malicious prompt. Delimit evidence in prompts, retain server-side controls, and red-team the eventual LLM integration. |

## Production controls still required

| Area | Required implementation / operational evidence |
| --- | --- |
| Identity | OIDC/MSAL token signature, issuer, audience, expiry and tenant validation; MFA/conditional access; revocation and least-privilege role assignment; distinct reviewer identities. |
| Authorization | Tenant/record-level policy plus PostgreSQL RLS; Qdrant pre-search ACL filtering; authorization on every MCP tool; service identities distinct from human identities. |
| Network | TLS, private endpoints where appropriate, gateway/WAF quotas, trusted reverse-proxy configuration, outbound destination allowlists, DNS/redirect-aware SSRF protection, no metadata-service access. |
| Secrets and encryption | Secret manager/workload identity, rotation, no secrets in prompts/traces, KMS encryption and key separation, least-privilege S3/Azure/database credentials. |
| Runtime isolation | Non-root containers, read-only filesystem, resource quotas, isolated model workers, process-level deadlines, patched base images, sandboxed document parsing. |
| Data governance | Dataset lineage and source permissions, purpose-limited feature access, quarantine/schema evolution, UTC semantics, retention/deletion schedules and legal holds where applicable, indexed-copy deletion propagation. |
| Model governance | Artifact hashes/signatures and dependency locks; golden prediction parity; frozen preprocessing; time-based validation; calibration, drift, fairness and reviewer-capacity thresholds; model approval/version rollback. |
| Retrieval quality | Approved-source ingestion, document/chunk provenance, HNSW recall benchmarks, held-out NDCG/MRR/Recall, RRF/BGE comparisons, stale-evidence detection, no cross-domain joins without verified mappings. |
| AI runtime | Durable LangGraph checkpoints, actual token/cost/iteration reservations, provider-content filters, redacted Langfuse traces, structured-output validation, groundedness/abstention evaluations. |
| Human control | Durable review queue, reviewer permission checks, four-eyes separation where needed, evidence/version-bound decisions, optimistic concurrency, retry-safe resume, audit of overrides and escalation. |
| Audit and operations | Non-owner runtime database role, external immutable/WORM audit archive, read/security-event retention, SIEM alerts and incident playbooks, measurable SLOs, staged rollout and rollback. |
| Resilience | Tested backup/restore and recovery objectives, dependency isolation, persistent jobs/outbox, bounded retries with jitter, dead-letter handling, replay tests, disaster-recovery drills. |
| Supply chain | Locked dependencies, vulnerability and static-analysis gates, secret scanning, reviewed dependency updates, signed image/SBOM pipeline, required branch checks and independent review. |

These are engineering requirements, not a certification. Applicability of financial, privacy, or payment regulations must be assessed for an actual deployment and jurisdiction.

## Showcase

Run the synthetic demo without cloud credentials, real data, or a running database:

```powershell
uv sync --frozen --python 3.11
uv run python scripts/demo_guardrails.py
```

The report separates live API checks from policy-library checks and exits nonzero on failure. `docs/GUARDRAIL_DEMO_REPORT.json` is a captured example from the verified run; rerun to regenerate evidence.

With the local service running, authenticated `GET /v1/guardrails` lists active controls, limits, integration-only policies, and pending deployment work. Use `/docs` to demonstrate 401, 403, 413, 429, and the model-unavailable response with synthetic inputs.

Run the full adversarial suite and actual PostgreSQL audit/concurrency checks:

```powershell
uv run python scripts/test_with_local_postgres.py --bin-dir 'C:\Program Files\PostgreSQL\17\bin'
uv run bandit -r src -q
uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file .test-runtime/runtime-requirements.txt
uv run pip-audit -r .test-runtime/runtime-requirements.txt --no-deps --disable-pip
```

For interviews: “I implemented and tested API and model-boundary guardrails, then built a separate fail-closed agent policy layer. I distinguish enforced controls from deployment requirements and validate attacks with reproducible tests.” Avoid claiming enterprise deployment, complete prompt-injection prevention, or compliance from a local demo.

## Reference framework

- [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/): authorization, resource consumption and configuration risks.
- [OWASP API4 resource consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/): bound request and workload resources.
- [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/): layered defenses and human approval; RAG alone is insufficient.
- [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/): limit tool functionality, permissions and autonomy.

The mapping supports threat coverage; it does not establish OWASP certification or comprehensive security.

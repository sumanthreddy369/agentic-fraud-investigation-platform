# Agentic Fraud Investigation Platform

This repository provides a guarded FastAPI service around the existing IEEE-CIS, Home Credit, and Elliptic risk model boundaries. It stores investigation cases and model-score provenance in PostgreSQL, supports validated ONNX inference, and defines a policy layer for future agent-driven investigations.

**Status:** In development. The API, persistence, guardrails, and ONNX adapter are implemented. External agents, retrieval, graph services, AWS deployment, and human-review workflows remain targets.

[Public repository](https://github.com/sumanthreddy369/agentic-fraud-investigation-platform) | [CI runs](https://github.com/sumanthreddy369/agentic-fraud-investigation-platform/actions)

---

## Repository structure

```text
.
├── src/risk_platform/                    # API and guarded runtime package
│   ├── __init__.py                       # Package version metadata
│   ├── main.py                           # FastAPI factory, routes, and exception handlers
│   ├── runtime.py                        # Uvicorn entry point and Windows loop setup
│   ├── config.py                         # RISK_* settings and validation
│   ├── contracts.py                      # Strict Pydantic API contracts
│   ├── authorization.py                  # Role, action, and domain permissions
│   ├── http_guardrails.py                # Request limits, deadlines, headers, and logging
│   ├── database.py                       # Async engine, ORM records, and sessions
│   ├── service.py                        # Case, audit, idempotency, and score persistence
│   ├── scoring.py                        # Registry, timeout, lock, and circuit breaker
│   ├── adapters.py                       # Adapter protocol and unavailable fallback
│   ├── onnx_adapter.py                   # ONNX manifest validation and inference
│   ├── agent_policy.py                   # Bounded investigation policy library
│   └── control_catalog.py                # Static guardrail inventory
├── migrations/                           # Alembic schema management
│   ├── env.py                            # Async migration environment
│   ├── script.py.mako                    # Migration template
│   └── versions/
│       ├── 0001_cases.py                 # Cases, audit events, and audit trigger
│       └── 0002_model_scores.py          # Score provenance and score trigger
├── tests/                                # Fast SQLite and optional PostgreSQL tests
│   ├── conftest.py                       # Fixtures and isolated PostgreSQL schemas
│   ├── test_api.py                       # Routes, persistence, replay, and scoring
│   ├── test_guardrails.py                # HTTP, authorization, and validation controls
│   ├── test_agent_policy.py              # Tool, evidence, and report policy
│   ├── test_onnx_adapter.py              # Generated ONNX model and provider tests
│   └── test_postgres.py                  # Migrations, triggers, and restart tests
├── scripts/
│   ├── demo_guardrails.py                # Synthetic 14-check guardrail demo
│   └── test_with_local_postgres.py       # Disposable PostgreSQL test runner
├── docs/
│   ├── BASELINE_INVENTORY.md             # Original assets and preservation rules
│   ├── DATASETS.md                       # Dataset locations and handling policy
│   ├── GUARDRAILS.md                     # Enforcement and threat-model detail
│   ├── GUARDRAIL_DEMO_REPORT.json        # Captured synthetic demo output
│   ├── ONNX_INFERENCE.md                 # Manifest and provider behavior
│   ├── AWS_TARGET_ARCHITECTURE.md        # Unimplemented AWS target status
│   ├── DEPENDENCY_AUDIT.json             # Dependency and capability inventory
│   └── PROGRESS.md                       # Incremental implementation record
├── .github/workflows/ci.yml              # Python 3.11 CI jobs
├── .env.example                          # Local configuration template
├── .gitignore                            # Secret, data, model, and output exclusions
├── compose.yaml                          # Loopback-only PostgreSQL 17 service
├── alembic.ini                           # Alembic configuration
├── pyproject.toml                        # Package, scripts, dependencies, and tools
├── uv.lock                               # Locked Python dependency graph
├── AGENTIC_FRAUD_PLATFORM_PLAN.md        # Incremental target plan
├── README.md                             # Code map, flows, commands, and status
├── AGENTS.md                             # Instructions for coding agents
└── CLAUDE.md                             # Pointer to AGENTS.md
```

---

## HTTP request admission

```mermaid
flowchart TD
    subgraph Boundary["ASGI boundary"]
        Client["HTTP client"] --> Guard["GuardrailMiddleware.__call__"]
        Guard --> Framing{"Headers and framing valid?"}
        Framing -->|no| Reject["Reject with bounded 4xx or 5xx"]
        Framing -->|yes| Capacity{"Rate and concurrency capacity available?"}
        Capacity -->|no| RejectCapacity["Reject with 429 or 503"]
        Capacity -->|yes| Host["TrustedHostMiddleware"]
    end
    subgraph Access["Route access"]
        Host --> Protected{"Route is under /v1?"}
        Protected -->|no| Public["Health or enabled docs handler"]
        Protected -->|yes| Actor["actor dependency"]
        Actor --> Token{"Configured bearer token matches?"}
        Token -->|token not configured| Unavailable["503 authentication unavailable"]
        Token -->|missing or invalid| Unauthorized["401 unauthorized"]
        Token -->|valid| Permission["AuthorizationPolicy.require"]
        Permission --> Allowed{"Role and domain allowed?"}
        Allowed -->|no| Forbidden["403 forbidden"]
        Allowed -->|yes| Handler["FastAPI route handler"]
    end
    subgraph Response["Response boundary"]
        Public --> Headers["Security headers and request ID"]
        Handler --> Headers
        Headers --> Log["Structured request log"]
        Log --> Caller["HTTP response"]
    end
```

The outer middleware rejects malformed or oversized traffic before route code runs. Identity and permissions come from server configuration, so request headers cannot select an operator or role.

**Framing and limits:** `GuardrailMiddleware` rejects ambiguous framing, compressed bodies, non-JSON writes under `/v1`, oversized headers or bodies, and slow body reads. It does not trust `X-Forwarded-For`.

**Capacity:** Rate limiting uses one process-local fixed window. Concurrency admission fails immediately when the configured semaphore is full. These controls do not coordinate across workers.

**Authentication:** `/v1` uses one configured bearer token. An empty token disables protected routes with `503`. Token comparison uses constant-time byte comparison.

**Errors and logs:** Validation responses omit submitted values. Database and unhandled errors return generic messages. Logs contain route templates and timings, not bodies or exception strings.

**Status: Complete.** Distributed rate limiting, proxy identity, and external identity providers are not built. See [docs/GUARDRAILS.md](docs/GUARDRAILS.md).

---

## Case creation and idempotency

```mermaid
flowchart TD
    Request["POST /v1/cases"] --> Contract["CaseCreate validation"]
    Contract --> Access["AuthorizationPolicy.require"]
    Access --> Switch{"Writes enabled?"}
    Switch -->|no| Disabled["503 writes disabled"]
    Switch -->|yes| Create["CaseService.create"]
    Create --> Domain{"Domain allowed?"}
    Domain -->|no| Denied["403 domain access denied"]
    Domain -->|yes| Hash["Canonical request SHA-256"]
    Hash --> Existing{"Owner and idempotency key exist?"}
    Existing -->|yes| Match{"Request hash matches?"}
    Match -->|yes| Replay["Return existing case with 200"]
    Match -->|no| Conflict["409 idempotency conflict"]
    Existing -->|no| Insert["Insert CaseRecord"]
    Insert --> Audit["Insert case.created AuditEvent"]
    Audit --> Commit["Commit one transaction"]
    Commit --> Created["Return new case with 201"]
    Insert -->|unique-key race| Rollback["Rollback and reload winner"]
    Rollback --> Match
```

Case creation binds the idempotency key to the owner and a canonical hash of the validated request. The case row and its initial audit event commit together.

**Validation:** Domains are `ieee_cis`, `home_credit`, and `elliptic`. Unknown fields are rejected. Strings and identifiers are stripped and bounded.

**Idempotency:** The same owner, key, and payload returns the original row. Reusing the key with another payload returns `409`. A database constraint resolves concurrent first writes.

**Isolation:** Reads filter by configured owner and allowed domains. Inaccessible cases return `404`. List pagination and offsets are bounded.

**Status: Complete.** Case mutation beyond creation is not exposed.

---

## Case-scoped model scoring

```mermaid
flowchart TD
    Request["POST /v1/cases/{case_id}/scores"] --> Contract["ModelScoreCreate validation"]
    Contract --> Case["CaseService.get"]
    Case --> Found{"Accessible case exists?"}
    Found -->|no| Missing["404 case not found"]
    Found -->|yes| Hash["Canonical request hash"]
    Hash --> Existing{"Score idempotency key exists?"}
    Existing -->|yes| Same{"Request hash matches?"}
    Same -->|yes| Replay["Return stored score with 200"]
    Same -->|no| Conflict["409 idempotency conflict"]
    Existing -->|no| Gateway["ScoringGateway.score"]
    Gateway --> Result{"Valid result returned?"}
    Result -->|no| Error["Return bounded error"]
    Result -->|yes| Record["CaseService.record_score"]
    Record --> ScoreRow["Insert ModelScoreReference"]
    ScoreRow --> Audit["Insert model.score_recorded AuditEvent"]
    Audit --> Commit["Commit one transaction"]
    Commit --> Created["Return score with 201"]
    ScoreRow -->|unique-key race| Rollback["Rollback and reload winner"]
    Rollback --> Same
```

The route resolves the case through owner and domain filters before inference. It stores successful model output as provenance without persisting submitted feature values.

**Case binding:** The score domain must equal the case domain. The configured role must allow case access and score creation.

**Replay:** An exact replay returns the stored result without another model call or audit event.

**Provenance:** The row contains model and schema versions, positive-class meaning, backend, artifact SHA-256, actor, request hash, and UTC time.

**Atomicity:** The score row and `model.score_recorded` event commit together. PostgreSQL triggers reject score and audit updates or deletes.

**Status: Complete.** Production model artifacts still need verified manifests.

---

## Model loading and ONNX inference

### Adapter startup

```mermaid
flowchart TD
    Settings["Settings.onnx_manifests"] --> Registry["build_model_registry"]
    Registry --> Defaults["UnavailableAdapter for each domain"]
    Defaults --> Configured{"Manifest configured?"}
    Configured -->|no| Keep["Keep unavailable adapter"]
    Configured -->|yes| Load["load_onnx_adapter"]
    Load --> Contract["OnnxModelManifest validation"]
    Contract --> Artifact["Resolve artifact and calculate SHA-256"]
    Artifact --> Hash{"Hash and suffix valid?"}
    Hash -->|no| Invalid["Install InvalidConfiguredAdapter"]
    Hash -->|yes| Runtime["Import onnxruntime"]
    Runtime --> Providers{"Providers available and active?"}
    Providers -->|no| Invalid
    Providers -->|yes| Session["InferenceSession"]
    Session --> IO{"Tensor metadata valid?"}
    IO -->|no| Invalid
    IO -->|yes| Ready["Install OnnxPredictionAdapter"]
```

The registry starts fail-closed for all three preserved domains. A configured adapter replaces its fallback only after artifact, provider, and tensor checks pass.

**Manifest:** The manifest fixes domain, model and schema versions, path and hash, ordered features, tensor names, output mode, positive-class index, and provider order.

**Providers:** CPU, CUDA, and OpenVINO are accepted. The requested primary provider must activate. Windows imports OpenVINO before ONNX Runtime provider setup.

**Failure:** Adapter-load errors keep the domain unavailable with a generic reason. Paths and runtime internals do not enter API responses.

### Scoring

```mermaid
flowchart TD
    Request["ScoringGateway.score"] --> Enabled{"Domain allowed and scoring enabled?"}
    Enabled -->|no| Reject["403 or 503"]
    Enabled -->|yes| Busy{"Domain lock available?"}
    Busy -->|no| BusyError["503 model busy"]
    Busy -->|yes| Circuit{"Circuit open?"}
    Circuit -->|yes| CircuitError["503 circuit open"]
    Circuit -->|no| Adapter["PredictionAdapter.score"]
    Adapter --> Features{"Exact numeric feature set?"}
    Features -->|no| SchemaError["422 feature schema error"]
    Features -->|yes| Tensor["Build float32 batch tensor"]
    Tensor --> Thread["asyncio.to_thread session.run"]
    Thread --> Output["Normalize configured output"]
    Output --> Result["ScoreResult validation"]
    Result --> Identity{"Domain and versions match?"}
    Identity -->|no| ContractError["502 invalid model response"]
    Identity -->|yes| Success["Return probability and provenance"]
    Adapter -->|timeout| Timeout["504 model timeout"]
    Adapter -->|repeated failure| Open["Open per-domain circuit"]
```

The gateway permits one in-flight call per domain and moves blocking inference to a worker thread. It validates the adapter result again before returning it.

**Features:** Names must match the manifest exactly. Values are reordered to manifest order. Booleans, nonnumeric values, missing fields, and extras fail validation.

**Outputs:** One output is accepted. Supported scalar and probability shapes depend on the manifest. Probabilities must be finite and within `[0, 1]`.

**Circuit:** Failures count toward a per-domain threshold. The circuit opens for a configured cooldown. Success resets it. Inference is not retried.

**Status: Partial.** The adapter and gateway are complete. No production model binary or manifest is committed, so domains are unavailable by default. See [docs/ONNX_INFERENCE.md](docs/ONNX_INFERENCE.md).

---

## Guarded investigation policy

```mermaid
flowchart TD
    Start["GuardedInvestigation.run"] --> Owner{"Actor matches case owner?"}
    Owner -->|no| Denied["AgentPolicyViolation"]
    Owner -->|yes| External{"External AI requested?"}
    External -->|yes| Egress{"Public data and egress approved?"}
    Egress -->|no| Denied
    Egress -->|yes| Plan["InvestigationPlan validation"]
    External -->|no| Plan
    Plan --> Calls["Execute ToolCall items sequentially"]
    Calls --> Budget{"Allowlist, domain, count, and time valid?"}
    Budget -->|no| Denied
    Budget -->|yes| Tool["Bounded tool executor"]
    Tool --> Evidence["EvidenceItem validation"]
    Evidence --> Scope{"Case, domain, owner, and ID valid?"}
    Scope -->|no| Denied
    Scope -->|yes| More{"More calls within budget?"}
    More -->|yes| Calls
    More -->|no| Draft["InvestigationDraft validation"]
    Draft --> Citations{"Citations and disposition valid?"}
    Citations -->|no| Denied
    Citations -->|yes| Packet["InvestigationPacket"]
    Packet --> Review["requires_human_review is true"]
```

The policy treats tools, model output, and evidence as untrusted. It returns a packet only after scope, budget, evidence, and citation checks pass.

**Tools:** Allowed names are `get_case_evidence`, `search_policy`, and `get_graph_neighborhood`. Graph lookup is Elliptic-only. Calls run sequentially with bounded arguments, count, and duration.

**Evidence:** A run accepts at most 20 items. Excerpts are bounded. Every item must match the active case, domain, and owner. Conflicting duplicate IDs fail the run.

**External AI:** External inference is disabled by default. When enabled, the plan must declare public data and explicit egress approval. A basic sensitive-data pattern check still applies.

**Reports:** Citations must refer to collected evidence. A report without evidence must use `insufficient_evidence`. Every packet requires human review.

**Status: Partial.** Contracts and tests exist. No LangGraph runtime, MCP server, tool implementation, external model call, persistence, or reviewer endpoint is connected.

---

## Database migration and readiness

```mermaid
flowchart LR
    subgraph Migration["Schema migration"]
        Command["uv run alembic upgrade head"] --> Env["migrations/env.py"]
        Env --> First["0001_cases"]
        First --> Second["0002_model_scores"]
        Second --> Schema["Cases, audits, and score references"]
        Schema --> Triggers["PostgreSQL immutability triggers"]
    end
    subgraph Runtime["Readiness check"]
        Probe["GET /health/ready"] --> Revision["Read alembic_version"]
        Revision --> Current{"Revision is 0002_model_scores?"}
        Current -->|no| NotReady["503 schema_mismatch"]
        Current -->|yes| Table["Probe CaseRecord table"]
        Table --> Available{"Query succeeds?"}
        Available -->|no| DatabaseError["503 database_unavailable"]
        Available -->|yes| Ready["200 ready"]
    end
```

Alembic owns schema evolution. Runtime readiness requires the exact head revision and a successful case-table query.

**PostgreSQL:** The async psycopg engine uses bounded pooling, pre-ping, connection and statement timeouts, a lock timeout, and an idle-transaction timeout.

**SQLite:** SQLite supports fast tests. It does not install PostgreSQL triggers, so trigger behavior is covered by marked integration tests.

**Time:** `UTCDateTime` rejects naive values and normalizes aware values to UTC.

**Status: Complete.** The head is `0002_model_scores`. Managed database provisioning is not included.

---

## Continuous integration

```mermaid
flowchart TD
    Push["Push or pull request"] --> Core["test job on Python 3.11"]
    Push --> OpenVINO["openvino job on Python 3.11"]
    subgraph CoreChecks["Core job"]
        Core --> Sync["uv sync with onnx-cpu"]
        Sync --> Ruff["Ruff lint and format check"]
        Ruff --> Pytest["pytest"]
        Pytest --> Demo["demo_guardrails.py"]
        Demo --> Bandit["Bandit scan"]
        Bandit --> Export["Export locked runtime requirements"]
        Export --> Audit["pip-audit"]
    end
    subgraph ProviderChecks["OpenVINO job"]
        OpenVINO --> OpenVINOSync["uv sync with onnx-openvino"]
        OpenVINOSync --> AdapterTests["test_onnx_adapter.py"]
    end
```

CI separates the CPU suite from the OpenVINO provider check. The committed workflow does not start PostgreSQL, so marked integration tests require a local run.

**Locked installs:** Both jobs use `uv.lock` with `--frozen`. The CPU and OpenVINO extras conflict because they install different ONNX Runtime packages.

**Security:** Bandit scans `src`. `pip-audit` checks a locked runtime requirements export.

**Status: Complete.** Lint, format, tests, the demo, security scans, and provider tests are configured.

---

## Build requirements

| Requirement | Version or constraint | Source |
|---|---|---|
| Python | `>=3.11,<3.14` | `pyproject.toml` |
| uv | Must accept the committed lock | `.github/workflows/ci.yml` |
| PostgreSQL | 17 for the committed local service | `compose.yaml` |
| Docker Compose | Needed only for the container database path | `compose.yaml` |
| ONNX Runtime CPU | Optional `onnx-cpu` extra | `pyproject.toml` |
| OpenVINO runtime | Optional `onnx-openvino` extra; Windows only | `pyproject.toml` |

The repository has no `apt`, Homebrew, Winget, or Chocolatey installer. Install Python, uv, Docker, and any native PostgreSQL distribution through the OS first.

**Windows PowerShell:**

```powershell
uv sync --frozen --python 3.11 --extra onnx-cpu
Copy-Item .env.example .env
docker compose up -d --wait
```

**Linux and macOS shell:**

```bash
uv sync --frozen --python 3.11 --extra onnx-cpu
docker compose up -d --wait
```

Create `.env` from `.env.example` with the file-copy command supplied by the shell. The declared OpenVINO extra is Windows-only.

---

## Building and running

There is no separate compile step. Hatchling packages `src/risk_platform`, and `uv sync` installs the project.

1. Install the locked CPU environment.

   ```powershell
   uv sync --frozen --python 3.11 --extra onnx-cpu
   ```

2. Copy the configuration and set `RISK_API_TOKEN` to at least 32 characters.

   ```powershell
   Copy-Item .env.example .env
   ```

3. Start PostgreSQL and migrate it.

   ```powershell
   docker compose up -d --wait
   uv run alembic upgrade head
   ```

4. Start the loopback-only API.

   ```powershell
   uv run risk-platform
   ```

The server binds to `127.0.0.1:8000`. Swagger UI exists at `/docs` only when `RISK_DOCS_ENABLED=true`.

### Environment variables

Settings use the `RISK_` prefix and may be loaded from `.env`.

| Variable | Purpose | Default or rule |
|---|---|---|
| `RISK_ENVIRONMENT` | Runtime profile | `local`; accepts `local` or `test` |
| `RISK_DATABASE_URL` | Async SQLAlchemy URL | Local PostgreSQL URL in `.env.example` |
| `RISK_API_TOKEN` | Bearer token | Empty disables `/v1`; configured value needs 32 characters |
| `RISK_OPERATOR_ID` | Actor and owner | `local-operator` |
| `RISK_OPERATOR_ROLE` | Role | `investigator`; also `reviewer` or `auditor` |
| `RISK_ALLOWED_DOMAINS` | Accessible domains | All three preserved domains |
| `RISK_ONNX_MANIFESTS` | JSON domain-to-manifest map | Empty map |
| `RISK_SCORING_ENABLED` | Scoring kill switch | `true` |
| `RISK_WRITES_ENABLED` | Persistence kill switch | `true` |
| `RISK_DOCS_ENABLED` | OpenAPI and Swagger switch | `true` |
| `RISK_ALLOWED_HOSTS` | Trusted hosts | `localhost`, `127.0.0.1`, `testserver` |
| `RISK_MAX_BODY_BYTES` | Body limit | `65536` |
| `RISK_MAX_HEADER_BYTES` | Header limit | `16384` |
| `RISK_BODY_TIMEOUT_SECONDS` | Body deadline | `5` |
| `RISK_REQUESTS_PER_MINUTE` | Per-peer rate | `120` |
| `RISK_RATE_LIMIT_MAX_CLIENTS` | Rate-map bound | `1024` |
| `RISK_MAX_CONCURRENT_REQUESTS` | Admission limit | `20` |
| `RISK_MODEL_TIMEOUT_SECONDS` | Inference timeout | `5` |
| `RISK_MODEL_FAILURE_THRESHOLD` | Circuit threshold | `3` |
| `RISK_MODEL_COOLDOWN_SECONDS` | Circuit cooldown | `30` |

---

## Commands / binaries / scripts

| Command | Purpose |
|---|---|
| `uv sync --frozen --python 3.11 --extra onnx-cpu` | Install the locked CPU development environment |
| `uv sync --frozen --python 3.11 --extra onnx-openvino` | Install the locked Windows OpenVINO environment |
| `docker compose up -d --wait` | Start PostgreSQL 17 on loopback |
| `uv run alembic upgrade head` | Apply migrations through `0002_model_scores` |
| `uv run risk-platform` | Start `risk_platform.runtime:serve` |
| `uv run pytest -q` | Run fast tests and any configured PostgreSQL tests |
| `uv run pytest -q tests/test_onnx_adapter.py` | Run generated-model adapter tests |
| `uv run python scripts/demo_guardrails.py` | Run the synthetic guardrail demo |
| `uv run python scripts/test_with_local_postgres.py --bin-dir "C:\Program Files\PostgreSQL\17\bin"` | Run all tests on a disposable cluster |
| `uv run ruff check .` | Run lint checks |
| `uv run ruff format --check .` | Check formatting |
| `uv run bandit -r src -q` | Scan Python source |
| `uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file /tmp/risk-runtime-requirements.txt` | Export CI runtime requirements |
| `uv run pip-audit -r /tmp/risk-runtime-requirements.txt --no-deps --disable-pip` | Audit exported runtime dependencies |

---

## API / usage

### Health endpoints

Liveness does not touch the database.

```http
GET /health/live HTTP/1.1
Host: 127.0.0.1:8000
```

Readiness verifies the exact Alembic head and the cases table.

```http
GET /health/ready HTTP/1.1
Host: 127.0.0.1:8000
```

### Protected routes

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/models` | List adapter and circuit state |
| `POST` | `/v1/models/{domain}/score` | Score features without case persistence |
| `POST` | `/v1/cases` | Create a case and initial audit event |
| `GET` | `/v1/cases` | List accessible cases |
| `GET` | `/v1/cases/{case_id}` | Read one scoped case |
| `GET` | `/v1/cases/{case_id}/audit` | Read audit events |
| `POST` | `/v1/cases/{case_id}/scores` | Score a case and store provenance |
| `GET` | `/v1/cases/{case_id}/scores` | List stored score provenance |
| `GET` | `/v1/guardrails` | Return the static control catalog |

Every `/v1` request uses the configured token:

```http
GET /v1/models HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer replace-with-the-configured-token
```

Create a case with an idempotency key:

```http
POST /v1/cases HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer replace-with-the-configured-token
Idempotency-Key: case-example-001
Content-Type: application/json

{
  "domain": "ieee_cis",
  "source_record_id": "transaction-1001",
  "title": "Manual review requested"
}
```

Score a configured model:

```http
POST /v1/models/ieee_cis/score HTTP/1.1
Host: 127.0.0.1:8000
Authorization: Bearer replace-with-the-configured-token
Content-Type: application/json

{
  "features": {
    "TransactionAmt": 125.0
  }
}
```

The feature map must match the manifest. Without a valid manifest, the domain returns `503`.

**Control-catalog limitation:** `/v1/guardrails` is static metadata. Its release value and some pending-provider labels lag the package version and AWS target documents. Runtime behavior and the status table below are authoritative.

---

## Feature status

| Feature | Status |
|---|---|
| FastAPI factory, routes, and loopback runtime | Complete |
| Strict Pydantic API and model contracts | Complete |
| Request guardrails and structured logging | Complete |
| Local bearer authentication and role/domain authorization | Complete |
| PostgreSQL cases, audit events, and score provenance | Complete |
| Idempotent case and score writes | Complete |
| PostgreSQL append-only triggers | Complete |
| Alembic migrations and revision-aware readiness | Complete |
| ONNX Runtime and OpenVINO adapter validation | Complete |
| Model timeout, lock, and circuit breaker | Complete |
| Production model binaries and manifests | Stubbed |
| IEEE-CIS, Home Credit, and Elliptic artifact integration | Partial |
| Guarded investigation policy contracts | Partial |
| Static control-catalog metadata | Partial |
| PostgreSQL execution in GitHub Actions | Target (not built yet) |
| LangGraph agents and supervisor | Target (not built yet) |
| MCP tool servers | Target (not built yet) |
| Bedrock or Azure OpenAI invocation | Target (not built yet) |
| Human-review API and durable investigation packets | Target (not built yet) |
| Qdrant or pgvector, BM25, hybrid search, RRF, and BGE reranking | Target (not built yet) |
| Neptune graph features and GraphRAG | Target (not built yet) |
| Kafka or Kinesis and S3 ingestion | Target (not built yet) |
| Glue, Spark, EMR, Feast, MLflow, and SageMaker pipelines | Target (not built yet) |
| IAM, KMS, CloudWatch, Lambda, and API Gateway deployment | Target (not built yet) |
| OpenTelemetry, Langfuse, drift, and agent evaluation | Target (not built yet) |

Dataset and baseline details are in [docs/DATASETS.md](docs/DATASETS.md) and [docs/BASELINE_INVENTORY.md](docs/BASELINE_INVENTORY.md). The intended AWS evolution is in [docs/AWS_TARGET_ARCHITECTURE.md](docs/AWS_TARGET_ARCHITECTURE.md) and [AGENTIC_FRAUD_PLATFORM_PLAN.md](AGENTIC_FRAUD_PLATFORM_PLAN.md).

---

## Testing

The default suite uses SQLite and generated ONNX fixtures. PostgreSQL tests skip when `RISK_TEST_DATABASE_URL` is absent.

```powershell
uv run pytest -q
```

Run CI lint and format checks:

```powershell
uv run ruff check .
uv run ruff format --check .
```

Run the guardrail showcase:

```powershell
uv run python scripts/demo_guardrails.py
```

Run all tests against a disposable PostgreSQL installation on Windows:

```powershell
uv run python scripts/test_with_local_postgres.py --bin-dir "C:\Program Files\PostgreSQL\17\bin"
```

The runner creates a cluster under `.test-runtime`, selects a random loopback port and password, creates a database and isolated test schemas, redacts the password, and stops the cluster.

| Test file | Coverage |
|---|---|
| `tests/test_api.py` | Routes, model state, persistence, replay, and score provenance |
| `tests/test_guardrails.py` | Auth, hosts, framing, limits, errors, and headers |
| `tests/test_agent_policy.py` | Tools, budgets, evidence, citations, egress, and review |
| `tests/test_onnx_adapter.py` | Hashes, manifests, features, outputs, CPU, and OpenVINO |
| `tests/test_postgres.py` | Migrations, constraints, triggers, concurrency, and restart |

The PostgreSQL fixture accepts only `postgresql+psycopg` URLs and drops only its randomized schema.

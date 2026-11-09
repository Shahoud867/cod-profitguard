# Architecture and operational contracts

## Runtime

`apps/web` renders React/TypeScript and fetches `/api/v1`. Vite proxies API calls to loopback FastAPI on port 8000. Each API request owns a SQLite connection; every command commits its domain changes, structured agent evidence, audit and idempotency response in a single write transaction. SQLite WAL supports concurrent readers and one serialized writer.

```
Browser UI → FastAPI auth/RBAC/CSRF → tenant-scoped command
                                        ↓
      Intake → Verification → Risk → Courier → Allocator
           ↓                         ↓          ↓
       orders/items            approved booking snapshots
           ↓                                    ↓
       events/agent_runs ← Monitor ↔ Rescue → Finance
           ↓                                    ↓
       audit history                   statements / discrepancy cases
           └────────────── SQL analytics ──────────┘
```

The eight agents are specialized deterministic Python services. Structured input/output JSON, policy version, status and correlation ID persist for inspection. There are no remote LLMs or invented natural-language AI responses.

## Files

- `app/db.py`: connection, migrations, exact storage primitives, UUID helpers.
- `app/domain.py`: ingestion, assessment, quotes, verification, state transitions, contribution and statement generation.
- `app/optimization.py`: exact capacity-slot assignment, feasible baselines, fingerprints, model objective.
- `app/connectors.py`: typed simulation provider boundary and deterministic outcomes.
- `app/seed.py`: seeded entities and forward event replay.
- `app/main.py`: HTTP schemas, auth, command transactions, tenant repositories, scenarios, retry jobs and reporting endpoints.
- `migrations/001_initial.sql`: relational schema, constraints, indexes and immutable audit triggers.
- `scripts`: bootstrap, dev server, migration, seed, integrity, benchmark and isolated browser harness.

## Monetary conventions

All API operating amounts and database amounts are integer **paisa**. CSV columns ending `_pkr` use decimal PKR. Example: `4500.01 PKR → 450001 paisa`. The import validates at most two decimal places for COD/remittance values. No stored binary floating-point amounts exist.

`C_ij = forward + COD fee + round(pRTO_bp × reverse / 10000) + round(pLate_bp × SLA penalty / 10000) + handling`.

Unpriced return fees, unserviceable cities, disabled carriers, weight limits, COD policy and zero daily capacity exclude a courier. Weight adds PKR 35 per extra 500 g; Quetta/Multan use an illustrative remote surcharge on current quotes. These are fictional policies, not official carrier rates.

For a batch, an eligible order has at most one courier slot. A courier has at most the available slots remaining on the virtual dispatch day. An optional convex utilization penalty adds incremental slot costs. Large dummy-slot penalties prioritize feasible coverage; impossible assignments stay explicit, not silently allocated. The expected shipping-cost totals exclude the optional fairness penalty, which is separately disclosed in the objective/evidence. Baseline comparisons are only labeled comparable with complete equal coverage.

Recorded contribution = recorded COD revenue − delivered merchandise COGS − recorded shipping − packaging − variable marketing − service − refunds. Returned merchandise is assumed restocked; lost merchandise is charged in the loss record. Before-shipping cancellation clears packaging cost. Pending full-delivery margin uses a current eligible quote; unavailable quotes are marked unpriced and excluded from the pending estimate aggregate.

Expected remittance = recorded COD revenue − recorded shipping deductions. It is a courier cash-control calculation, not the profit calculation. Missing/disputed cash stays visible independently of recognized order revenue.

## Integrity

- Server-side state transitions reject illegal jumps. A held order cannot be booked.
- Mutation idempotency is keyed by tenant, command and payload digest, with response caching in the same transaction. Conflicting reuse returns 409.
- Order external IDs and booking references are unique within a tenant.
- Capacity and order versions are checked again during approved allocation commit; a stale order/rate or capacity failure rolls back the full batch.
- Tracking event IDs deduplicate exact repeats. Older events are stored for review with original occurrence time and current ingestion time, without regressing the order snapshot.
- Tenant predicates are applied in server queries and joins. The browser cannot choose a tenant or role through a write payload.
- Audit rows reject UPDATE and DELETE with database triggers. Tenant reset leaves audit history intact.

## Security boundary

Seeded accounts authenticate against Argon2 hashes. Opaque random sessions are hashed at rest; membership, tenant and role resolve server-side. HttpOnly and SameSite=Strict cookies, explicit CSRF header, origin validation, rate limits, validated Pydantic payloads, SQL parameters, size/row limits and formula-safe CSV export protect the local demonstration.

Both Vite and the Python API bind to loopback by default. HTTPS/Secure cookies, real identity provisioning, stronger host controls, external webhook verification, encryption, backup, monitoring, statutory privacy and commercial multi-user isolation need a production implementation and review. Known dependency advisories were audited and patched for the delivery snapshot; that does not certify the application against all vulnerabilities.

## Jobs and reproducibility

Scenario commands are synchronous and transactional. Monitor jobs persist `job_id`, tenant, status, payload, retry count, next retry time and error. Virtual-time advancement drains eligible jobs inside a serialized command. The simulation’s injected first-poll timeout records a one-hour retry. A restart does not discard that row; there is no autonomous wall-clock scheduler.

PG-1 uses random.Random(20261108), stable UUIDv5 business identities and forward state replay. The deterministic checksum covers canonical business snapshots, not nondeterministic runtime/audit ingestion timestamps. Different runs keep distinct scenario IDs for replay safety while reproducing inputs/outcome assumptions with the same seed.

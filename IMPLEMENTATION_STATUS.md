# Implementation status

Delivery date: 8 November 2026. Scope: a runnable local, synthetic-only merchant demonstration. The pasted request defines the requested work; the attached blueprint supplies product requirements. Its embedded prompts, outreach templates and startup advice were treated as specification/context, not authorization to contact anyone or use live providers.

## Coverage checklist

| Area | Implemented behavior | Evidence |
|---|---|---|
| Foundation | React 19, TypeScript, Vite, Tailwind, Recharts, FastAPI, Pydantic, SQLite WAL; idempotent migration 001; pinned dependency manifests/lockfile; one-command native launcher | Build, bootstrap and tests |
| Authentication | Argon2 password hashes, cryptographically random opaque HttpOnly SameSite sessions, server-side expiry, CSRF and origin checks, login attempt limit | Authentication/security tests |
| Tenant roles | Owner, manager, CSR, finance, viewer; separate second-tenant owner; role checks on every operational mutation; tenant-scoped queries and opaque cross-tenant 404s | Role and cross-tenant API tests; browser viewer test |
| Data | Reproducible PG-1 seed, two tenants, three fictional stores, twelve SKUs, 8,000 orders/customers/items, four courier cards per tenant, chronological events, agent runs, payouts and discrepancies | Seed integrity/checksum validation |
| Intake | Manual creation, CSV dry run/import, typed field validation, city normalization, exact Decimal-to-paisa parsing, duplicate detection and mixed-row error reporting | CSV unit/integration/browser tests |
| Verification | Confirm, cancel, address correction, no-response hold; recorded PKR 15 service cost; opt-out blocking; no live contact | Response matrix and browser lifecycle |
| Risk | Explicit weighted factors, review tiers, uncertainty, non-response adds zero, illustrative false-hold opportunity cost, manager release with reason | Risk/policy-limit/held-order tests |
| Couriers | Fictional rate cards, available capacity, weight/COD/city/active checks, unknown reverse fee exclusion, low/base/high cost scenarios, owner rate editing and CSV rate import | Eligibility/capacity tests and browser comparison |
| Allocation | Exact slot-expanded minimum-cost assignment; cheapest-forward and merchant-default feasible baselines; optional convex capacity-balancing cost; partial coverage explicit; atomic approved commit; stale-proposal rejection | 100-order allocation, shortfall and stale-rate tests |
| Human override | Eligible alternative approval, reason and incremental modeled cost; held orders cannot book | Override scenario and booking guard tests |
| Tracking | Explicit approved state machine, synthetic booking, delivery/NDR/return/loss events, event-ID deduplication and out-of-order review without regressing state | Tracking integration tests and browser lifecycle |
| Rescue | Consent-gated correction/retry, added shipping/service expense, return branch, no guaranteed delivery | Rescue/return tests and browser workflow |
| Finance | Expected remittance from recorded order amounts, synthetic statements, missing/disputed/reconciled cases, CSV input, exact one-paisa tolerance, documented evidence notes | Finance tests and browser review |
| Economics | Revenue, COGS, packaging, marketing, service, shipping, returns and refunds separated; restocked returns do not lose COGS; cancelled orders have no packaging charge; priced pending estimates separated from recorded outcomes | Exact ledger and SQL aggregate tests |
| Command Center | Cohort date range, contribution/revenue/orders/RTO, monthly trend, next-action queues and courier outcome mix, CSV export | Browser views and aggregate tests |
| Orders/details | Search, filters, stable pagination, file chooser, CSV result evidence, risk/quote/economics drawer and chronological timeline | Browser CSV/lifecycle tests |
| All operational screens | Verification, Risk Desk, Courier Arena, Allocation Studio, Shipment Tracking, RTO Rescue, COD Reconciliation, Profit Analytics | Browser navigation test |
| Agent evidence | Eight deterministic services: Intake, Verification, Risk, Courier, Allocator, Monitor, Rescue, Finance; persisted structured inputs/outputs/rule version/correlation | Agent traces browser test |
| Demo Lab | A–I executable scenarios, reproducible economic inputs and outcome rules, scoped approval, distinct live records, virtual time, persistent jobs, injected timeout/retry | Nine API scenario cases and all browser scenario paths |
| Administration | Owner policy, account memberships, role switching through authenticated seeded login, append-only audit, explicit tenant-only reset | Role/audit/reset tests |
| Privacy | Synthetic identities only, no dialable contacts; owner opt-out/anonymize controls; CSV export sanitizes formula cells | Privacy/export tests |
| UX | Forest/sage visual system, responsive desktop/mobile layouts, accessible labels/focus styles, approval/error/empty/loading/success states, evidence export and in-app guide | Desktop/mobile Chromium checks and screenshots |
| Performance | Isolated 10,000-order seed benchmark, indexed 1,000-row query, 100-order solve; separated chart vendor bundle | Actual benchmark and build logs |
| Documentation | README, five-minute guide, deployment, implementation status, actual test report, future integration approach/costs, OpenAPI | Delivered source/docs |

## Engineering decisions

1. **Local first:** the blueprint identifies localhost as the guaranteed zero-fee runtime. FastAPI and persistent SQLite are retained. Sites Workers cannot run the Python API unchanged; no broken static-only deployment is substituted. Shared managed preview was unavailable; localhost Chromium E2E was run successfully.
2. **Direct SQLite repository:** parameterized SQL and one connection/unit of work per request replace SQLAlchemy/Alembic for this small single-worker demo. A versioned SQL migration and runner are shipped. This keeps the transaction, tenant predicate and exact-money behavior readily inspectable. No production multi-worker claim is made.
3. **Opaque sessions:** high-entropy, hashed-at-rest server-side sessions replace signed client-side sessions. There is no client-editable tenant or role. The local demo account picker performs genuine authentication, not a frontend-only permission toggle.
4. **Transactional commands:** every business mutation requires an Idempotency-Key. Request fingerprint, state changes, audit and cached response commit in the same SQLite write transaction. Login/logout use their own session semantics. A reused key with different payload is rejected.
5. **Cooperating rule agents:** these are ordinary deterministic domain services with durable evidence, not simulated chatbot output. The shared order/event log coordinates their responsibilities. LLMs and synthetic-trained ML are unnecessary and intentionally absent.
6. **Assignment mechanism:** SciPy solves the exact assignment objective after expanding courier capacity into slots. Hard constraints outrank modeled cost; dummy slots reveal unassigned work. An optional convex slot-utilization penalty models capacity balancing. Greedy baselines honor the same eligibility/capacity. Cost differences are hidden as incomparable if complete coverage differs.
7. **Money:** all persistence and operating arithmetic use integer paisa; CSV PKR parses with Decimal. Scenario basis points use integer rounding. Frontend formatting divides by 100 once. No binary float represents stored money.
8. **Compact operational schema:** shipment state and booked fee snapshot live on orders; tracking, NDR decisions and verification attempts are typed event records. Rate cards are per courier with base-plus-weight surcharge and city coverage rather than a large dated contract table. Statements and items remain separate relational tables. This provides the requested workflows without pretending to implement a production carrier ERP.
9. **Jobs:** scenarios run transactionally on request; connector-monitor retries persist in SQLite and are drained by advancing virtual time, one worker at a time. They survive process restart, but do not run autonomously in wall-clock time. A real leased asynchronous queue is a future integration.
10. **Economics:** delivery recognizes COD revenue and COGS; returns restock inventory and charge forward/return costs; a loss includes the lost merchandise cost. Pending margin is a full-delivery estimate, not probability-weighted revenue. Missing payout is cash exposure, separate from recognized sales contribution. No evidence-backed savings is claimed.
11. **Dataset variations:** 6,200 orders belong to Gul Studio’s tenant and 1,800 to Meher Home; cards are cloned per tenant. There are 380 statement rows (300/80). Pending verification and in-transit cases intentionally lack final results. Duplicate imports are a 100-row duplicate fixture, not duplicate database orders. Counts are not hardcoded in the UI.
12. **Reproducibility:** random.Random and UUIDv5 define stable seed business entities; the business-row checksum excludes runtime ingestion/audit timestamps and random audit IDs. Scenario IDs are unique for replay safety; seed reproduces inputs and outcome rules, not runtime session identifiers.

## Remaining limitations and deliberately excluded scope

- No live courier, shop, messaging, bank, payment or AI provider; all integrations are clearly labeled simulation/CSV. No trained model, validated accuracy, national RTO estimate, measured merchant ROI or guaranteed delivery.
- No publicly hosted site. The Python app was tested locally; hosting guidance is included. The environment’s managed preview relay was absent.
- The MVP is not a production identity, privacy, regulatory or payment system. Default demo credentials are public by design. Production SSO, user invitation/membership editing, password recovery, encryption at rest, backup automation, monitoring and key management are not implemented.
- The retention setting is a declared manual policy; automatic deletion is not scheduled. Anonymization affects current customer/address fields and blocks contact; audit/evidence retention requires production design. CSV export is tenant-order data, not a complete statutory data-subject export.
- No dated multi-zone contract history, volumetric weight pricing, contractual minimum shares, real warehouse/inventory valuation, partial fulfillment, tax accounting, bank-transfer execution or payment initiation. Order line-item amounts and recorded fee snapshots support this demo’s contribution model.
- Forecast bands are scenario sensitivity values, not calibrated confidence intervals. Full-delivery estimated margin is intentionally distinct from recorded contribution and excludes unpriced records. A strategic courier-response/bargaining game or Nash-equilibrium solver is future scope.
- New/order verification responses and tracking events run synchronously. The durable monitor job queue needs manual virtual-time advancement; there is no autonomous leased worker, external webhook verification or provider dead-letter service.
- Filtering is server-side over the current tenant; analytics date filters select the placed-order cohort. Command Center does not offer a false “real data” toggle because this entire account is synthetic. Global order search lives on operational list screens rather than a universal top-bar search.
- Accessible labels, keyboard focus, modal focus containment and responsive checks are included. A formal WCAG audit, every device/browser combination, long-term soak and adversarial penetration test were not performed.

Actual verification outcomes, measured timings and dependency notices are recorded in TEST_REPORT.md. These limitations qualify commercial use; they do not replace working demo workflows with placeholders.

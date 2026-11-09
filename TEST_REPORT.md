# Actual test report

Tested 8 November 2026 on this managed Linux executor. Python 3.12.14, Node 24.22.1, system Chromium through Playwright. This report records executed checks, not a promised test plan.

## Final automated results

| Check | Actual result |
|---|---|
| `pytest services/api/tests -q` | **48 passed**, 2 dependency deprecation warnings, 27.56 seconds |
| `npm test` | **3 passed**, 1 Vitest file |
| `npm run test:e2e` | **10 passed**, 58.5 seconds including isolated app startup/seed |
| `npm run build` | TypeScript and Vite production build passed; 1,995 modules transformed |
| `python -m compileall -q services/api/app` | Passed |
| PG-1 seed validation | 8,000 orders, referential integrity and financial invariants passed |
| Independent seed reproducibility | Two independently seeded databases have the same canonical business checksum |
| `npm audit --json` | **0 known vulnerabilities** in final frontend dependency graph at scan time |
| `pip-audit -r services/api/requirements.txt` | **No known vulnerabilities found** in the final resolved Python requirements at scan time |

Total: **61 passing automated test cases** (48 API/domain/security + 3 frontend formatting + 10 browser tests). No failing automated tests remain in the delivery snapshot.

## API / domain / security coverage

Actual tests cover:

- Authentication, HttpOnly sessions, expiry, CSRF, hostile origin, required idempotency keys, attempt limiting, viewer/CSR/finance/owner boundaries.
- Cross-tenant opaque 404s for orders, risk execution, rate edits, settlements and allocation commits, plus filtered list isolation.
- CSV dry run, creation, duplicate references, mixed invalid rows, exact paisa precision, over-limit COD review, formula-safe export.
- Confirm/cancel/address-change/non-response flows, service costs, explicit human approval, review factors, legitimate false-hold release, held-order dispatch blocking and unoverrideable COD policy limits.
- Unknown zones, missing reverse prices, capacity shortfall, feasible 100-order exact optimization, both baseline objectives, atomic commit and stale-rate invalidation.
- Illegal shipment jumps, exact event deduplication, ten out-of-order events retained chronologically without state regression.
- NDR retry permission, exact retry/service costs, successful delivery contribution, returns without double-counted restocked COGS.
- Missing/mismatched/matched remittances, statement CSV rejects unknown references, one-paisa tolerance and no accidental rewriting of sales/transport costs.
- SQL-derived analytics reconcile to source orders and city/courier sums.
- All nine Demo Lab scenarios run and persist operational records; H has reproducible delivered/returned outcomes; I audits its override.
- Durable connector timeout/retry, owner privacy controls and opt-out enforcement, owner reset that preserves the other tenant and append-only audit, pending quote completeness.

## Browser tests

Chromium exercised:

1. All requested views, including the order detail drawer; no captured JavaScript page errors.
2. CSV validation, search and evidence timeline.
3. New order → confirm → per-courier comparison → approved simulated booking.
4. 100-order exact allocation → separate human approval → persisted batch booking.
5. NDR → customer-approved retry → out for delivery → delivered.
6. Finance discrepancy review that remains disputed when the reported amount differs.
7. Remaining A/B/C/D/H/I scenarios and actual structured agent evidence.
8. Viewer read access and disabled operational controls.
9. A 390 × 844 viewport, working navigation, horizontally scrollable tables, no document overflow and a full-width drawer.
10. Desktop, Demo Lab and mobile screenshots with animations settled/disabled.

Browser tests use a disposable database by default; they leave the working merchant database untouched. Screenshots intentionally show the test cohort after scenario operations, so their order/KPI values differ from the pristine bundled seed. The command-center date range filters the placed-order cohort, not the full dataset count.

## Measured performance

The isolated `scripts/benchmark.py` generated 10,000 orders and checked foreign keys. On this executor:

| Measurement | Actual |
|---|---:|
| 10,000-order seed | 18.506 s |
| Warm filtered SQL query returning 1,000 records, 20 repetitions | median **19.525 ms**, max **54.272 ms** |
| Exact allocation for 100 ready orders | **0.152 s**, 100 assigned |

These are executor-specific SQL/solver measurements. They do not include browser rendering, HTTP/network latency, a slower merchant laptop or production concurrency. Browser functional tests verify the actual API/UI separately. This is not a claim of real-world courier prediction accuracy or merchant savings.

## Data and build evidence

Pristine dataset: 8,000 orders/customers/items; 59,679 operational events; 23,295 agent runs; 380 statement rows; 2 tenants, 3 stores, 12 SKUs, and 8 tenant-owned courier cards representing 4 fictional carrier models.

Canonical PG-1 business checksum:

```
818b28198b7d8ab564f3c64693fde342d084c2ff6ce201d61c6eeaed88a4881b
```

10,000-order benchmark business checksum:

```
50dbeb8c512c3b58a479d798494cdabafeca65a76a1f36ecc0316be821bb4dbe
```

Final frontend output is split into an approximately 262 KB application chunk and 418 KB chart/vendor chunk (about 79 KB / 115 KB gzip), plus CSS. Values are build artifacts, not runtime records.

Raw logs, final audit JSON, benchmark JSON and the Playwright JSON report are included under `docs/verification/`. Desktop/mobile screenshots are in `docs/`.

## Defects fixed during verification

- Checkpoint/close the SQLite template before copying it into API test fixtures; avoids a first-test WAL snapshot issue.
- Correct navigation test selectors to accommodate live count badges.
- Price new pending orders before estimating margin and explicitly exclude unpriced cases.
- Disable chart entry animation and wait for settled sidebar position in screenshot captures.
- Use an isolated temporary database for repeatable browser suites.
- Update Vite, Vitest, Playwright, PostCSS, FastAPI, Starlette and pytest after dependency audit findings. Re-executed functional/security/browser checks and builds after the updates.
- Bind the local frontend/API to loopback; no externally reachable demo server is intentionally left running.

## Outstanding limits / notices

- The environment’s managed `sites-preview` relay returned “preview relay unavailable: No such file or directory”. No shared/public hosted app was verified or published. A local Chromium/Playwright server was successfully exercised; these are distinct facts.
- Two final Python test warnings concern upstream TestClient/httpx and AnyIO deprecations. They do not fail the suite; migration to the newer upstream client interface is future maintenance.
- Dependency scans report known advisories at a point in time. They are not a security certification or penetration test.
- Formal WCAG compliance, production load/soak, real-provider behavior, real data protection and live economic benefit are unverified. Detailed scope limitations are in IMPLEMENTATION_STATUS.md.

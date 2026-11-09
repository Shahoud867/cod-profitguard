# Five-minute merchant demonstration

All examples are fictional. Start as **Owner**, with a fresh PG-1 dataset. Use the guide inside the top toolbar during the demo. Never frame the synthetic RTO rates, model assumptions or cost comparisons as measured merchant savings.

| Time | Screen / action | Merchant takeaway |
|---|---|---|
| 00:00–00:45 | Command Center. Read recorded contribution, revenue, RTO denominator and action queues. Open Profit Analytics briefly. | Contribution includes recorded costs; pending estimates stay separate. |
| 00:45–01:30 | Demo Lab → A → approve run → Inspect order → Confirm → approve response. Open Courier comparison. | A real order record enters a validated state machine. Explain why an apparently cheap forward fee can hide return costs. |
| 01:30–02:45 | Demo Lab → E → approve run → View allocation. Inspect 100 routes, capacities and cheapest/default baselines. Approve batch → check approval → Approve & book. | Exact assignment honors eligibility and daily capacity. This is a hypothetical cost comparison, not proven savings. |
| 02:45–03:45 | Demo Lab → F → approve run → Inspect order → Correct & retry. Record customer approval, correct the address, approve. Then record Out For Delivery and Delivered, or NDR followed by RTO and Returned. | A retry costs PKR 35 plus PKR 15 service time; delivery is uncertain. Customer permission is required. |
| 03:45–04:30 | Demo Lab → G → approve run. Open COD Reconciliation. Review a missing or disputed row. Record an actual amount and evidence note. | A payout mismatch stays disputed; amounts within one paisa of expected reconcile. Finance review never rewrites the sales ledger. |
| 04:30–05:00 | Demo Lab → H → approve full-lifecycle run. Inspect order, Profit Analytics and Agent Traces. | A persisted outcome changes contribution and settlement records. Every specialized agent has inspectable inputs and outputs. |

## Extra demonstrations

**B — Verification:** choose confirm, cancel, address_change or no_response in the scenario selector. Each response writes events. Non-response alone adds zero risk points and never causes an automatic fraud classification.

**C — Legitimate customer edge case:** an incomplete address triggers +35 review points. Use Address Change to correct it, or a manager release with reason after review. Inspect hypothetical false-hold opportunity cost.

**D — Courier trade-off:** inspect F + pRTO × R + pLate × L + COD fee + H; inspect low/high scenario assumptions and exclusions. These are not statistical confidence intervals.

**I — Human override:** the preapproved scenario selects an eligible alternative and audits its incremental modeled cost. For a manual override, open any ready order → Courier comparison → Select & approve courier → choose an alternative → explain your reason → approve.

**CSV:** Orders → Import CSV. The example starts in dry-run mode. Inspect evidence to see accepted/rejected/duplicate row results. Uncheck Validate only to create records. `data/fixtures/orders-mixed.csv` includes 100 duplicate rows, incomplete addresses, invalid fields and a policy-limit case. The file picker also loads a local CSV into the preview.

**Rate cards:** Courier Arena → Edit simulated rate card (owner), or import `data/fixtures/courier-rates.csv`. An unknown reverse fee excludes the carrier. A rate change invalidates an old proposal.

**Adapter failure:** inspect an active order → Test adapter timeout. Demo Lab → Advance 24 hours records a retry; advance again to complete the durable job. No automatic shipment or contact is invented.

**Roles and isolation:** sign out, choose Viewer to inspect disabled write controls; choose Other tenant to see the isolated Meher Home workspace. CSR can verify and rescue; finance can resolve remittances; manager approves routing; owner changes policy and resets.

**Privacy:** owner → order detail → Manage demo consent & privacy. Opt out blocks simulated contact. Anonymize removes the fictional name/address from operational records and preserves financial and audit evidence. This is a demo control, not a complete production erasure process.

## Reset and repeat

Settings & audit → Reset demo → type `RESET SYNTHETIC DATA` → approve. This restores only the current tenant’s initial seed, rates and virtual clock. Audit history remains append-only. Repeated scenario runs create distinct records; the same scenario seed reproduces economic inputs/outcome rules rather than reusing order identifiers.

After allocating many batches, advance virtual time by one day to free the next day’s capacity. Held/unverified orders are never eligible for booking. A policy-limit order cannot be released merely by overriding its risk score.

## Honest pitch

“ProfitGuard shows a transparent way to compare COD operating decisions. These records, couriers and assumptions are simulated. We would need your authorized rate cards, shipment outcomes and remittances to measure whether this improves contribution per placed order in your business.”

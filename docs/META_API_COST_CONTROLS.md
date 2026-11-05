# Meta Model API: Budget-Controlled Gateway & Safeguards

This document specifies the cost-control architecture, rate formulas, reservation lifecycle, and fail-closed security invariants governing the Meta Model API integration in Filament.

---

## 1. Core Principles

1. **Pay-as-you-go Protection**: All calls to the Meta Model API consume promotional/funded account credits. Cost control is a hard architectural boundary.
2. **Fail-Closed by Default**: The integration is disabled out of the box (`MODEL_API_ENABLED=false`). If any check fails, uncertainty occurs, or the budget is exhausted, requests are rejected immediately.
3. **No Direct Requests**: All features must route through the centralized `MetaModelGateway`. Direct SDK or arbitrary HTTP calls from frontend or backend modules are prohibited.
4. **Pre-Flight Atomic Reservation**: Estimated costs are calculated and committed to a durable database ledger *before* sending any bytes across the network.
5. **Zero Assumptions on Timeouts**: Network timeouts or ambiguous provider outcomes are marked `UNKNOWN` and quarantined. Their reserved funds are **never** assumed free or refunded without manual reconciliation.

---

## 2. Pricing & Rate Assumptions

Rates reflect Meta's official Standard mode for `muse-spark-1.3` (verified as of **November 2026**):

| Model | Input Rate (per 1M tokens) | Output Rate (per 1M tokens) | Effective Per-Token Input | Effective Per-Token Output |
| :--- | :--- | :--- | :--- | :--- |
| **`muse-spark-1.3`** | **$1.25** | **$4.25** | `$0.00000125` | `$0.00000425` |

### Cost Calculation Formula

$$\text{Cost (USD)} = \frac{\text{Input Tokens} \times 1.25}{1{,}000{,}000} + \frac{\text{Output Tokens} \times 4.25}{1{,}000{,}000}$$

Computed using Python's `Decimal` type quantized to 6 decimal places (`0.000001` USD) to prevent floating-point underestimation.

---

## 3. Server-Side Configuration

Configured via environment variables (`.env`), validated on application startup:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MODEL_API_KEY` | *(empty string)* | Meta API Bearer Key. Must exist only on server, never returned in API payloads or logged. |
| `MODEL_API_BASE_URL` | `https://api.meta.ai/v1` | Base URL for Meta Model API endpoints (`/responses`). |
| `MODEL_API_MODEL` | `muse-spark-1.3` | Default allowlisted model name. |
| `MODEL_API_ENABLED` | `false` | Master kill-switch. Gateway rejects requests when `false`. |
| `MODEL_API_LIFETIME_BUDGET_USD` | `100` | Maximum lifetime USD spend ceiling across all requests. |
| `MODEL_API_DAILY_BUDGET_USD` | `5` | Maximum USD spend allowed within any rolling 24-hour window. |
| `MODEL_API_INITIAL_TEST_BUDGET_USD` | `5` | Initial testing phase spending limit. |
| `MODEL_API_MAX_REQUEST_COST_USD` | `0.10` | Hard cap on the maximum reservation cost for a single request. |
| `MODEL_API_MAX_INPUT_TOKENS` | `20000` | Maximum estimated input tokens per request. |
| `MODEL_API_MAX_OUTPUT_TOKENS` | `2000` | Maximum reserved output tokens per request. |
| `MODEL_API_MAX_CONCURRENT_REQUESTS`| `1` | Strict concurrency lock (1 in-flight request at a time). |

---

## 4. Lifecycle: Reservation & Reconciliation

```
[Incoming Request]
        │
        ▼
[Pre-flight Validation]
  ├─ Enabled? (MODEL_API_ENABLED == True)
  ├─ API Key configured?
  ├─ Model allowlisted?
  ├─ Input tokens <= 20,000?
  └─ Output tokens <= 2,000?
        │ Passed
        ▼
[Conservative Token Estimation]
  └─ Conservative heuristic + 20% safety margin + 10 tokens
        │
        ▼
[Atomic Database Reservation (Transaction)]
  ├─ In-flight concurrency check (count(RESERVED) < 1)
  ├─ Spending uncertainty check (count(UNKNOWN) == 0)
  ├─ Single request cost check (<= $0.10)
  ├─ Lifetime budget check (Committed + Est <= $100.00)
  ├─ Daily budget check (Committed 24h + Est <= $5.00)
  └─ Test budget check (Committed + Est <= $5.00)
        │
        ▼
  Insert row: status='RESERVED', reserved_cost_usd=Est
        │
        ▼
[POST https://api.meta.ai/v1/responses]
        │
   ┌────┴───────────────────────────┬────────────────────────────┐
   │ Success (200 OK)               │ Provider Error (4xx/5xx)   │ Timeout / Ambiguous
   ▼                                ▼                            ▼
[Reconcile Success]              [Reconcile Failure]          [Mark UNKNOWN]
- Read actual tokens from        - Set status='FAILED'        - Set status='UNKNOWN'
  response.usage                 - Release reserved_cost      - KEEP reserved_cost locked
- Compute exact actual_cost        (actual_cost=0.0)          - Quarantine all further
- Set status='SUCCEEDED'                                        requests until resolved!
- Release unused reservation
```

---

## 5. Distinction: Application Budget vs. Meta Billing Alerts

> [!WARNING]
> **Meta Billing Alerts Are Not Hard Caps:**
> Meta's billing console provides optional threshold alerts (e.g., notify at \$50). **These alerts do not stop API traffic or prevent charges.** If an unbounded loop occurs, charges continue until account credits are exhausted or credit cards are charged.
>
> In contrast, Filament's **Durable Spending Ledger is a hard, fail-closed barrier**. It validates database records before making any HTTP connection and terminates execution before credit is spent.

---

## 6. How to Inspect & Control Spending

### Immediate Kill Switch
To stop all Meta API activity instantly without database access:
```bash
export MODEL_API_ENABLED=false
```
Or set `MODEL_API_ENABLED=false` in `.env` and reload the application.

### Visibility Endpoints
Authorized agents can inspect usage without exposing secrets:
- `GET /api/v1/model-usage/budget`: Lifetime, daily, test budgets, actual spend, pending reservations, and remaining headroom.
- `GET /api/v1/model-usage/records`: Audit log of individual inference requests, tokens, and micro-costs.
- `GET /api/v1/model-usage/by-model`: Aggregated token usage and spend grouped by model.
- `GET /api/v1/model-usage/by-feature`: Aggregated token usage and spend grouped by calling feature.

---

## 7. What These Safeguards Cannot Guarantee

1. **Meta Account Access Outside Filament**: These safeguards apply only to requests dispatched through the Filament backend. Any external scripts, curl commands, or other tools using the same `MODEL_API_KEY` are not tracked by this ledger.
2. **Provider Upstream Rate Changes**: If Meta alters pricing without updating `MODEL_PRICING_REGISTRY`, actual billing from Meta could diverge from recorded local accounting. Verify rates periodically against Meta developer documentation.


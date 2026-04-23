# FM-09 — Silent Retry Multiplication

**Severity:** costly
**First observed:** any agent loop with provider-side retries
**Frequency in our ops:** occasional

## Diagnosis

A request fails (timeout, rate limit, transient 500). The SDK or
the agent loop transparently retries. Two or three retries
succeed, but the failed attempts each consumed full input tokens.
The cost ledger records only the successful attempt; the
provider's bill records all of them. Bill > ledger.

## Observable symptoms

- Discrepancy between local cost-tracker totals and provider's
  invoice.
- Provider dashboard shows N requests for a session your ledger
  records as N/2.
- Latency spikes on certain turns with no apparent cause (the
  retries serialize behind a backoff).
- Inconsistent cache_hit_rate readings — the retried request may
  hit cache while the original missed.

## Mitigations

1. **Primary** — log every retry as a separate ledger entry with
   a `retry_of: <parent_request_id>` field; do not fold retries
   into the parent. See [`token-budget-tracker`](../../token-budget-tracker/).
2. **Secondary** — surface retry counts in the daily report
   (`token-budget-launchd`). A sudden rise in retry rate is a
   provider-side signal worth knowing about.

## Related

(Standalone — most other FMs are about agent reasoning; this is
about plumbing.)

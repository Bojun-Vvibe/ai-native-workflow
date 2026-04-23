# Cache economics — quick reference

A compact table of input / output / cached-input pricing for major coding
agent models. Use it to estimate the savings from cache discipline before
committing to a long-running mission.

> All prices are USD per million tokens (MTok). Numbers are point-in-time
> reference values; **always cross-check against the provider's current
> pricing page before quoting them in a real cost estimate.** The table's
> purpose is shape and ratios, not authoritative billing.

## Table

| Model family            | Input ($/MTok) | Cached input ($/MTok) | Cache write ($/MTok) | Output ($/MTok) | Cache TTL |
|-------------------------|---------------:|----------------------:|---------------------:|----------------:|----------:|
| Anthropic Claude tier-1 |          15.00 |                  1.50 |                18.75 |           75.00 |     5 min |
| Anthropic Claude tier-1 (1h)| 15.00      |                  1.50 |                30.00 |           75.00 |       1 h |
| Anthropic Claude mid    |           3.00 |                  0.30 |                 3.75 |           15.00 |     5 min |
| Anthropic Claude small  |           0.80 |                  0.08 |                 1.00 |            4.00 |     5 min |
| OpenAI GPT large        |          10.00 |                  2.50 |                10.00 |           30.00 | session   |
| OpenAI GPT mid          |           2.50 |                  0.625|                 2.50 |           10.00 | session   |
| Google Gemini Pro       |           7.00 |                  1.75 |                 7.00 |           21.00 |     1 h   |
| Google Gemini Flash     |           0.30 |                  0.075|                 0.30 |            2.50 |     1 h   |

Notes on the columns:

- **Input** — what you pay per MTok of input tokens that are NOT served from
  cache. This is the cost without cache discipline.
- **Cached input** — what you pay per MTok of input tokens that ARE served
  from cache. Typically 10–25% of the standard input price.
- **Cache write** — a one-time surcharge the first time a prefix is cached.
  Some providers price this above standard input (Anthropic), some at
  parity (OpenAI).
- **Output** — output tokens are never cached. This column is unchanged
  by cache discipline; it's here so the input / output ratio is visible.
- **TTL** — how long the cache survives after the last hit before
  eviction. Critical for long-gap missions; a 5-min TTL is useless if your
  WPs are 10 minutes apart.

## Worked example: 20-WP PR triage mission

Assume:

- Stable prefix (system + tools + charter + profile + repo overview): **40K tokens**.
- Per-WP fresh input (PR diff + metadata): **20K tokens**.
- Per-WP output: **5K tokens**.
- Model: Anthropic Claude tier-1, 5-min TTL, WPs run within 5 min of each other.

### Without cache discipline

Each WP pays full input price for the prefix every time:

```
20 WPs × (40K prefix + 20K per-WP) × $15/MTok = 20 × 60K × $15 / 1,000,000 = $18.00 input
20 WPs × 5K output × $75/MTok                  = 100K × $75 / 1,000,000   = $7.50  output
                                                                  TOTAL  = $25.50
```

### With cache discipline

The prefix is cached once and served from cache for WPs 2–20:

```
WP 1 (cache write): 40K × $18.75/MTok = 40K × $18.75 / 1,000,000  = $0.75
WPs 1–20 fresh input: 20 × 20K × $15/MTok                          = $6.00
WPs 2–20 cached prefix: 19 × 40K × $1.50/MTok                      = $1.14
WPs 1–20 output: 20 × 5K × $75/MTok                                = $7.50
                                                            TOTAL = $15.39
```

**Savings: ~40%** ($25.50 → $15.39) on a single 20-WP run, with no quality
change. The savings scale with prefix size and WP count. On a 200-WP
refactor mission with a 100K prefix, the cache-disciplined version is 5–10×
cheaper than the naive version.

## Decision rules

- **Prefix < 5K tokens** — caching helps but the absolute savings are small.
  Worth doing for hygiene; not worth restructuring a workflow for.
- **Prefix 5K–50K tokens** — caching is the single biggest cost lever.
  Always worth the structural discipline.
- **Prefix > 50K tokens** — caching is mandatory. A non-cached 100K prefix
  on every turn is a cost incident, not a workflow.
- **WPs spaced > TTL apart** — the 5-min Anthropic default may not survive
  between WPs if humans gate each one. Use the 1-hour TTL tier or a
  provider with session-scoped caching.

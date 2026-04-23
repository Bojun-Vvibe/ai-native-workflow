# Token-budget report — 2026-04-22

Range: 2026-04-22 00:00:00 → 2026-04-23 00:00:00 (local)
Sessions: 4 · Total turns: 187 · Generated: 2026-04-23 09:00:11

## Summary

| Metric | Value |
|---|---|
| Total input tokens | 412,883 |
| Total output tokens | 71,204 |
| Cache read tokens | 308,221 |
| Cache write tokens | 41,002 |
| Cache hit rate | 0.747 |
| Estimated cost (USD) | $4.86 |

## By model

| Model | In (cache hit) | In (fresh) | Out | Cost |
|---|---:|---:|---:|---:|
| claude-opus-4.7    | 220,118 | 60,420 | 51,003 | $3.41 |
| claude-sonnet-4.5  | 88,103  | 32,800 | 18,200 | $1.21 |
| gpt-5-mini         | 0       | 11,442 | 2,001  | $0.24 |

## By phase

| Phase | Turns | In | Out | Cost |
|---|---:|---:|---:|---:|
| scout      | 42  | 78,200  | 9,400  | $0.78 |
| implement  | 91  | 241,003 | 41,210 | $2.91 |
| review     | 38  | 71,200  | 14,400 | $0.86 |
| arbiter    | 16  | 22,480  | 6,194  | $0.31 |

## Notable

- Mission `M-2026-04-22-W06` consumed 51% of the day's spend
  (98k in + 15k out). Worth a glance at the diff size.
- Cache hit rate dropped to 0.62 in the 14:00 hour — coincides with
  a system-prompt edit. Consider stabilizing the prefix.

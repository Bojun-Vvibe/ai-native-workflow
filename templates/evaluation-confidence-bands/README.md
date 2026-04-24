# Template: Evaluation confidence bands

Turn a list of per-item LLM eval scores into a **mean + bootstrap
confidence interval**, and refuse to declare a winner when two
candidates' CIs overlap. Stops you from chasing 0.02-point "wins"
that are pure sampling noise.

Stdlib only. Deterministic via injected `random.Random`.

## Why this exists

Default eval workflow:

1. Run prompt v3 on 50 items. Score = 0.80.
2. Run prompt v4 on 50 items. Score = 0.82.
3. Ship v4.

This is wrong. With n=50 the 95% CI on each is roughly
`[0.68, 0.90]`. The CIs overlap by 0.20 score-points. You did not
measure that v4 is better than v3 — you measured that you can't
tell. Shipping v4 because the point estimate is higher is a
ritual, not a decision.

This template gives you:

- A bootstrap CI (percentile method, stdlib-only) over the mean.
- A comparator that returns `a_wins` / `b_wins` / `refuse`.
- A tunable `overlap_margin` for "I'll tolerate this much overlap
  in exchange for moving faster."

## Contract

### Inputs

- `scores`: a non-empty sequence of floats in `[0, 1]`. Out-of-range
  raises `ValueError`. Empty raises `ValueError`.
- `rng`: a seeded `random.Random`. **Required**, not optional. We
  never touch the global RNG, so two runs with the same seed
  produce byte-identical output.
- `iters`: bootstrap iterations. Minimum 100. Default 2000.
- `alpha`: 1 − confidence. Default 0.05 (95% CI).

### Outputs

```python
@dataclass(frozen=True)
class CIBand:
    name: str
    n: int
    mean: float
    lower: float
    upper: float
    alpha: float
    iters: int

@dataclass(frozen=True)
class Comparison:
    a: str
    b: str
    a_mean: float
    b_mean: float
    overlap: float           # signed; >0 => CIs overlap
    overlap_margin: float
    decision: str            # "a_wins" | "b_wins" | "refuse"
    reason: str
```

### Decision rule

Let `overlap = min(a.upper, b.upper) - max(a.lower, b.lower)`.

- If `overlap > -overlap_margin`: `refuse`. The data does not
  justify a ranking.
- Else if `a.mean > b.mean`: `a_wins`.
- Else: `b_wins`.

`overlap_margin = 0.0` means "I require strict CI separation."
`overlap_margin = 0.02` means "I tolerate up to 2 score-points of
CI overlap before refusing."

## Determinism

- The bootstrap uses the injected `random.Random` only. No
  `random.choice` against the module-level RNG anywhere.
- The seed is the caller's responsibility. Both worked examples
  use seed `20260424`; if you want to reproduce them locally you
  will get byte-identical numbers.

## Statistical caveats (read once)

- This is a **percentile bootstrap**, not BCa. Good enough for
  "should I trust this ranking?" decisions, not for publication.
- For very small n (< 20) the CI under-covers; treat refuse as the
  default.
- Score must be in `[0, 1]` (binary correct / partial-credit
  rubric). For unbounded numeric metrics, normalize first.

## Files

- `confbands.py` — implementation, stdlib only.
- `examples/example_refuse_to_rank.py` — small n, candidates close.
- `examples/example_clear_winner.py` — larger n, candidates far apart.

## Worked example 1 — refuse to rank

n=50 each. v3 = 0.80, v4 = 0.82. The bootstrap shows the CIs
overlap by 0.20 score-points; the harness refuses to declare a
winner.

```
$ python3 examples/example_refuse_to_rank.py
prompt_v3: n=50 mean=0.8000 95%CI=[0.6800, 0.9000] (iters=2000)
prompt_v4: n=50 mean=0.8200 95%CI=[0.7000, 0.9200] (iters=2000)

compare('prompt_v3' vs 'prompt_v4'): means=0.8000/0.8200 overlap=+0.2000 margin=0.0 -> refuse
  reason: CIs overlap by +0.2000 (margin=0.0); ranking is not justified by the data
```

## Worked example 2 — clear winner

n=200 each. baseline = 0.70, candidate = 0.92. The CIs separate
cleanly and the harness declares `b_wins`.

```
$ python3 examples/example_clear_winner.py
baseline: n=200 mean=0.7000 95%CI=[0.6350, 0.7600] (iters=2000)
candidate: n=200 mean=0.9200 95%CI=[0.8800, 0.9550] (iters=2000)

compare('baseline' vs 'candidate'): means=0.7000/0.9200 overlap=-0.1200 margin=0.0 -> b_wins
  reason: b CI [0.8800,0.9550] is strictly above a CI [0.6350,0.7600]
```

## When to use this

- A/B comparing two prompts, two models, or two retrieval pipelines
  on a fixed eval set.
- Promoting a candidate from staging to prod and you want a
  fail-loud signal when the "win" is illusory.
- Reporting eval results in a doc and you want to stop writing
  "0.82 vs 0.80, +2 pts" as if it meant something.

## When not to use this

- Online eval with continuously arriving traffic — use sequential
  testing, not a one-shot bootstrap.
- Multi-arm comparisons where you need correction for multiple
  testing — this template only handles pairwise.

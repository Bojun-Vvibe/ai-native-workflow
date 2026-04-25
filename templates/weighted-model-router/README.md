# weighted-model-router

Deterministic, weight-respecting router for picking one of N model
backends per request. Stdlib-only (`hashlib`, `math`). The class is
pure: no I/O, no clocks, no global state — caller composes with
their own health-check, circuit-breaker, and cost-budget logic.

The naïve `random.choices(backends, weights=…)` implementation gets
two things wrong that this template fixes:

| Bug class | Naïve `random.choices` | This router |
|---|---|---|
| Same `route_key` lands on a different backend on retry | Yes — random is stateful, replay diverges | No — `route(key)` is a pure function of `(key, backends, weights)` |
| Adding a brand-new backend at weight=5 reshuffles ~all existing keys | Yes — every weighted-pick is independent | No — rendezvous (HRW) hashing only reroutes keys whose top-2 score straddled the changed bucket (`~5%` in the worked example, vs `~67%` for hash-mod) |

The selection rule is the standard weighted-rendezvous (HRW)
construction: for each candidate backend `b`, compute
`score(b) = b.weight / -ln(uniform_hash(route_key, b.name))` and
pick the backend with the maximum score. Lexicographic tiebreak on
`backend.name` makes the result fully deterministic even in the
zero-probability collision case. `_uniform_hash` clamps strictly
into `(0, 1)` so `-ln(u)` can never be `+inf`.

## When to use it

* Pin user X (or session X, or tenant X, or `route_key=prompt_hash`)
  to model A for the duration of an A/B without a sticky cookie / DB.
* Replay a recorded trace and have it land on the *same* backend it
  originally hit, so the replay actually reproduces the production
  behaviour (sibling of `tool-call-replay-log`).
* Drain one backend (`exclude={"model-A"}`) without invalidating
  every other key's assignment — only the keys that *were* on
  `model-A` need to move.
* Express "10× more traffic to A than to C" as `weight=10` vs
  `weight=1` and trust the long-run distribution to converge.

## API

```python
from router import Backend, WeightedRouter, NoEligibleBackend

router = WeightedRouter(backends=(
    Backend("model-A", weight=70),
    Backend("model-B", weight=20),
    Backend("model-C", weight=10),
))

result = router.route("user-42")
# RouteResult(backend='model-B', score=…, considered=3, excluded=())

# Drain a backend mid-flight (circuit-breaker open, cost cap hit, …)
result = router.route("user-42", exclude={"model-A"})

# Excluding everything fails loud — never silently fall back to random
try:
    router.route("user-42", exclude={"model-A", "model-B", "model-C"})
except NoEligibleBackend as e:
    ...
```

`Backend(weight=…)` raises `InvalidWeight` if `weight <= 0` or
non-finite — silent zero-weight backends are a correctness trap
(they'd never be chosen but also never error, so an operator's
typo is invisible). Duplicate backend names also raise.

## Sample run

Output of `python3 worked_example.py`, verbatim:

```
============================================================
weighted-model-router worked example
============================================================

[1] determinism (same key → same backend across calls)
  key=     'user-42'  → model-B  (consistent: True)
  key=     'user-99'  → model-C  (consistent: True)
  key= 'session-abc'  → model-A  (consistent: True)

[2] weight distribution over 10,000 synthetic keys
  model-A:  7016  (70.16%  target ~70%)
  model-B:  1954  (19.54%  target ~20%)
  model-C:  1030  (10.30%  target ~10%)

[3] stickiness: bump model-B weight 20 → 25
  reshuffled keys: 388 / 10000  (3.88%)
  (a hash-mod router would reshuffle ~67%; HRW reshuffles only keys whose top-2 score straddled model-B)

[4] exclusion: drain model-A, route 5 sample keys
  key=     'user-42'  → model-B  considered=2 excluded=('model-A',)
  key=     'user-99'  → model-C  considered=2 excluded=('model-A',)
  key= 'session-abc'  → model-B  considered=2 excluded=('model-A',)
  key=       'req-7'  → model-C  considered=2 excluded=('model-A',)
  key=      'req-13'  → model-B  considered=2 excluded=('model-A',)

[5] excluding everything raises NoEligibleBackend
  OK: NoEligibleBackend: all 3 backends excluded for key 'user-42'

============================================================
done
```

The 70/20/10 weights produce a 70.16/19.54/10.30 split over 10,000
synthetic keys — within ~0.5pp of the target. Bumping `model-B`
from 20 → 25 only reshuffles 388/10000 keys (~3.88%) — a hash-mod
router would have reshuffled roughly two thirds.

## Composes with

* `model-fallback-ladder` — fallback ladder is *sequential* (try A,
  on failure try B, on failure try C); this router is *probabilistic*
  (split traffic across A/B/C by weight). Use both together: the
  router picks the *first* backend; the ladder governs what to do
  when that backend fails.
* `tool-call-circuit-breaker` — when the breaker opens for a backend,
  pass that backend's name into `exclude=`. Other keys keep their
  existing assignments thanks to HRW stickiness.
* `tool-call-replay-log` — recorded `route_key` + recorded backend
  set → same backend on replay, so the replay actually reproduces
  the original side effects' upstream.
* `agent-cost-budget-envelope` — weight per backend can be derived
  from the envelope's per-model dollar cap (`weight = remaining_budget
  / per_call_cost`), so the router naturally drains expensive backends
  as their budget is consumed.

## Non-goals

* No health checks, no latency-aware reweighting, no real-time
  feedback. Caller owns those signals and reflects them via
  `weight` and `exclude=`.
* No persistence. Backend list is constructor-time; a fresh
  `WeightedRouter` is the same function as the previous one as long
  as the backend names + weights match.

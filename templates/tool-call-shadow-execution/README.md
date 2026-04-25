# tool-call-shadow-execution

Run a *candidate* tool implementation in **shadow mode** alongside the
*production* implementation. Production is the source of truth; the shadow
runs in parallel, its result is compared against production, disagreements
are recorded, and its side-effects are suppressed.

## Why

Replacing a tool the agent already depends on (file-search backend, leaner
HTTP client, tree-sitter parser swap) is high-risk: a subtle behavior
change becomes a silent regression that surfaces two missions later as
"the agent stopped finding files." Shadow execution lets you diff prod vs.
candidate on **real production traffic**, with **zero blast radius**, until
you have enough samples to flip the cutover safely.

This is **not** a traffic-split (`weighted-model-router`): the shadow's
result is **never** returned to the agent, and a candidate that is broken
(writes to the wrong path, double-charges a metered upstream) cannot do
harm — the side-effect contract is enforced by the harness.

## Inputs

- `prod_fn(args) -> Any` — the trusted, currently-shipping tool.
- `shadow_fn(args, guard) -> Any` — the candidate. MUST honor
  `guard.is_dry_run is True` and MUST NOT touch `guard.marker_path`.
- `marker_check() -> bool` — caller-provided post-hook that returns True
  iff the shadow violated the side-effect contract (touched the marker,
  made a network call, etc.). Pass `None` to skip.
- `shadow_timeout_s` (float) — hard cap on the shadow. A timeout is
  recorded as `shadow_timeout`, **never** as a disagreement.
- `comparator(prod, shadow) -> (reason, detail)` — defaults to a deep
  equality comparator with key-set diffing on dicts; pass a semantic one
  (set-equality on file lists, JSON-canonical equality, etc.) when needed.

## Outputs

`ShadowResult` per call, plus a rolling `ShadowStats`:

- `by_reason: dict[str, int]` over the closed enum below.
- `by_status: dict[str, int]` over `ok | timeout | raised | skipped | unsafe`.
- `disagreement_rate() -> float`.
- `samples: list[ShadowResult]` — bounded ring (default 16) of NON-equal
  observations. Equal results are not retained, so memory is bounded
  regardless of traffic volume.
- `safe_to_promote(min_samples, max_disagreement) -> bool` — vetoed by any
  `side_effect_violation`, regardless of thresholds.

### Reason enum (closed)

```
equal
prod_only_field           shadow is missing a key prod returned
shadow_only_field         shadow added a key prod doesn't return
value_mismatch            same shape, different value
type_mismatch             prod and shadow returned different Python types
prod_raised               prod errored; shadow comparison is moot
shadow_raised             shadow errored; agent unaffected
both_raised               both errored (often: shared upstream is down)
shadow_timeout            shadow exceeded shadow_timeout_s
side_effect_violation     shadow wrote despite guard.is_dry_run=True
```

## Properties

- Production runs first and synchronously. Its result is **always** what
  the caller gets back. Shadow failures, timeouts, and disagreements never
  block the call.
- Shadow runs in a caller-injected `ThreadPoolExecutor` (deterministic in
  tests; you choose the pool size and lifetime).
- If prod raised, the shadow result is **discarded** and the call is
  bucketed `prod_raised` — comparing a successful candidate against a
  failed prod produces noise, not signal.
- A `side_effect_violation` is treated as a **veto** in `safe_to_promote`,
  even if disagreement rate is 0%: a candidate that writes when it was
  told not to is unsafe to promote regardless of how often it agrees.
- Stdlib only.

## Usage

```python
from concurrent.futures import ThreadPoolExecutor
from shadow import ShadowRunner, SideEffectGuard

def prod_search(args):  ...
def shadow_search(args, guard):
    assert guard.is_dry_run
    ...

with ThreadPoolExecutor(max_workers=4) as ex:
    runner = ShadowRunner(executor=ex, shadow_timeout_s=0.5)

    for call in incoming_calls:
        result = runner.execute(
            call_id=call.id, tool_name="search_files", args=call.args,
            prod_fn=prod_search, shadow_fn=shadow_search,
            marker_check=my_marker_check,  # or None
        )
        agent_receives(result.prod_value)  # NEVER result.shadow_value

    if runner.stats.safe_to_promote(min_samples=500, max_disagreement=0.01):
        flip_cutover()
```

## Composes with

- `weighted-model-router` — once shadow gives you the disagreement budget
  and zero side-effect violations, the router can gradually take the
  candidate live (1% → 5% → 25%).
- `tool-call-result-validator` — wrap both `prod_fn` and `shadow_fn`
  outputs with the same validator so a comparator never sees a malformed
  shape it didn't expect.
- `agent-decision-log-format` — emit one log line per `ShadowResult` with
  `reason` in `extra` so a dashboard can plot disagreement rate over time.
- `partial-failure-aggregator` — when the shadow harness is itself
  fanning across N tools, the aggregator decides what "ready to promote"
  means across the whole tool surface.

## Non-goals

- Does **not** do canary deploys (1% / 5% / 25%). That is upstream
  policy; this template's contract is "0% prod-affecting, 100% observed."
- Does **not** sandbox the shadow. The `SideEffectGuard` is a lightweight
  contract + post-hook check, not a syscall jail. For network egress
  isolation, run the shadow in a process with a denylisted egress route
  and use `marker_check` to assert it never resolved a forbidden host.

## Run

```
python3 worked_example.py
```

## Example output

```
========================================================================
tool-call-shadow-execution :: worked example
========================================================================
  [c1] q='auth'    reason=equal                    status=ok       detail=
  [c2] q='render'  reason=equal                    status=ok       detail=
  [c3] q='cache'   reason=value_mismatch           status=ok       detail=differ at .hits: prod=['src/cache.py', 'src/cache_keys.py'] shadow=['src/cache.py']
  [c4] q='noop'    reason=shadow_only_field        status=ok       detail=keys only in shadow: ['score']
  [c5] q='slow'    reason=shadow_timeout           status=timeout  detail=exceeded 0.2s
  [c6] q='danger'  reason=side_effect_violation    status=unsafe   detail=shadow tool wrote despite is_dry_run=True

Report:
{
  "total": 6,
  "by_reason": {
    "equal": 2,
    "shadow_only_field": 1,
    "shadow_timeout": 1,
    "side_effect_violation": 1,
    "value_mismatch": 1
  },
  "by_status": {
    "ok": 4,
    "timeout": 1,
    "unsafe": 1
  },
  "disagreement_rate": 0.6667,
  "n_samples_kept": 4
}

safe_to_promote(min_samples=6, max_disagreement=0.10): False
safe_to_promote(min_samples=1, max_disagreement=1.0)  : False  (vetoed by unsafe)
sample buffer kept (no equals): ['shadow_only_field', 'shadow_timeout', 'side_effect_violation', 'value_mismatch']

DONE.
```

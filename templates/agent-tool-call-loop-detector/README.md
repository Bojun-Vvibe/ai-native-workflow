# agent-tool-call-loop-detector

Detect when an autonomous coding agent is stuck in a degenerate loop —
*before* dispatching the next tool call — so the host can break out,
escalate, or inject a corrective system message instead of burning
budget on the same call forever.

## Problem

Autonomous agents loop. Common shapes:

- **Exact repeat.** Same grep, same read_file, same http_get over and over
  because the model keeps re-deciding the same thing.
- **ABAB cycle.** "Read X, edit X, read X, edit X, …" — each side keeps
  undoing or re-checking the other.
- **No progress.** A long tail where every call is identical and nothing new
  is being learned.

A naive equality check on raw arg dicts misses semantically-equal calls
whose JSON serialization differs (key order, etc.). A naive "same name twice
in a row" check fires on legitimate batched work.

## Solution

A small, stdlib-only detector that runs *inside the host loop* before each
tool dispatch:

- Canonicalizes args via sorted-key JSON so `{a:1,b:2}` and `{b:2,a:1}` hash
  equal.
- Looks at the last `window` calls (default 8).
- Fires on three independent signals:
  1. `exact_repeat` — same `(tool, canonical_args)` ≥ `repeat_threshold` times.
  2. `abab_cycle` — alternating two-call pattern of length ≥ `cycle_min_len`
     in the tail.
  3. `no_progress` — the entire window collapses to a single distinct call.
- Returns a structured `LoopReport` (`looped`, `reason`, `detail`) so the
  host can log it, emit a metric, and decide whether to escalate.

## Files

- `template.py` — `ToolCall`, `LoopReport`, `detect_loop(...)`. Drop into
  any agent host loop; pure stdlib.
- `example.py` — five synthetic histories (one healthy, four pathological)
  fed through the detector.

## Worked example

```
$ python3 templates/agent-tool-call-loop-detector/example.py
agent-tool-call-loop-detector :: worked example
============================================================
[  ok] healthy_progress                           reason=ok
[LOOP] exact_repeat_same_grep                     reason=exact_repeat
         . call: grep::{"pattern":"TODO"}
         . count: 4
         . window: 8
[LOOP] abab_cycle_read_then_edit_same_file        reason=exact_repeat
         . call: read_file::{"path":"x.py"}
         . count: 3
         . window: 8
[LOOP] no_progress_single_call_only               reason=exact_repeat
         . call: list_dir::{"path":"."}
         . count: 3
         . window: 8
[LOOP] args_canonicalized_repeats_caught          reason=exact_repeat
         . call: http_get::{"headers":{"a":1,"b":2},"url":"https://example.test/"}
         . count: 3
         . window: 8
============================================================
scenarios=5 looped_detected=4 healthy=1
```

5 scenarios, 4 loops correctly flagged, 1 healthy progression correctly
passed through. The ABAB scenario is caught by the stronger `exact_repeat`
signal first (the pair has already repeated 3×); the dedicated
`abab_cycle` branch covers shorter alternations where neither key has
yet hit `repeat_threshold` on its own.

## Tuning

| Knob               | Default | When to raise                                    |
|--------------------|---------|--------------------------------------------------|
| `window`           | 8       | Long-horizon agents that legitimately revisit.   |
| `repeat_threshold` | 3       | Tolerate noisier exploration.                    |
| `cycle_min_len`    | 4       | Quieter alarms when 2-call cycles are normal.    |

## Where this fits

Pair with `agent-loop-iteration-cap` (hard wall on total iterations) and
`agent-step-budget-monitor` (cost / latency budgets). This template is the
*semantic* signal — "you are repeating yourself" — that fires long before
the hard cap.

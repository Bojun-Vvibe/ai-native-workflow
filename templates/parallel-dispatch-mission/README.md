# Template: Parallel-dispatch mission (multi-agent fan-out)

A mission pattern that **fans out one orchestrator into N independent
worker agents**, runs them in parallel against disjoint slices of the
work, and **fans the results back in** through a deterministic reducer.
Workers never talk to each other. The orchestrator never does the work.
The reducer is the only place merge logic lives.

## Why this pattern exists

When you ask one agent to "review all 40 open PRs" or "summarize all 60
issues filed this week," three failure modes dominate:

1. **Context exhaustion mid-task.** Halfway through PR 23, the agent has
   forgotten what it said about PR 4, and quality drifts.
2. **Latency stacks linearly.** 40 PRs × 90 s each = an hour of wall
   time for work that is embarrassingly parallel.
3. **Single-thread bias.** The model anchors on whatever it saw first
   and scores later items relative to that anchor instead of on absolute
   merit.

Fan-out fixes all three: each worker sees only its own slice, so context
stays small; workers run concurrently, so wall time is `max` not `sum`;
each worker scores in isolation, so anchoring is per-slice instead of
global. The reducer's job is the comparatively cheap one of normalizing
and merging structured outputs.

## When to use

- **Embarrassingly parallel** read-heavy tasks: PR triage, issue triage,
  log scan, doc review, dependency audit, dead-link sweep.
- The slices are **roughly equal in size** so worker latency is similar.
- The output of each worker is **a structured artifact** (YAML, JSON,
  fenced markdown) the reducer can mechanically merge.
- You have **idempotent workers** — re-running one slice produces the
  same artifact (or a strictly better one).

## When NOT to use

- The work has **cross-slice dependencies** — worker B needs worker A's
  output. Use [`scout-then-act-mission`](../scout-then-act-mission/) or
  a sequential chain instead.
- Slices are **wildly uneven** — one slice is 95% of the work. Parallel
  buys nothing; just run the long one.
- The reducer would itself be **as expensive as the workers** — at that
  point you have not parallelized, you have just moved the bottleneck.
- **Write-heavy** tasks with a shared resource (the same file, the same
  API rate limit, the same DB). Workers will conflict.

## Anti-patterns

- **Workers that read each other's output.** Once they do, you no longer
  have N independent workers — you have a chain pretending to be
  parallel, and the chain order is non-deterministic.
- **Stateful reducers.** The reducer should be a pure function of the
  worker artifacts. If it has to call back to the model for "judgment,"
  you have hidden a sequential review pass inside the reducer and lost
  the parallelism you paid for.
- **Unbounded fan-out.** 200 workers against the same external API will
  trip rate limits and cost more than the serial version. Cap fan-out
  at the smaller of (your token budget / per-worker tokens) and (the
  external API's burst limit).
- **Different prompts per worker.** If worker prompts diverge, you can't
  compare outputs. Keep the worker prompt identical; vary only the
  slice input.

## Files

- `mission.example.yaml` — wires one orchestrator, N workers, one
  reducer, with the slice-assignment contract.
- `prompts/orchestrator.md` — produces the slice manifest. Does no
  per-slice work.
- `prompts/worker.md` — single, identical prompt run N times with
  different slice inputs.
- `prompts/reducer.md` — deterministic merge of worker artifacts into
  one report.
- `examples/sample-fanout-pr-triage.md` — a worked run that fans out 12
  open PRs across 4 workers, reduces to a single ranked queue.

## The slice contract

The orchestrator MUST produce a `slices.yaml` shaped:

```yaml
fanout:
  worker_count: 4
  slice_assignment_strategy: "round_robin" | "size_balanced" | "by_label"
slices:
  - id: slice-1
    items: [PR#101, PR#107, PR#112]
  - id: slice-2
    items: [PR#102, PR#108, PR#113]
  # ...
```

Each worker is invoked once per slice and MUST produce
`worker-<slice_id>.yaml` with a fixed schema. The reducer reads all
`worker-*.yaml` files and produces one `report.md`. If any worker fails
or times out, the reducer MUST emit the partial report AND a
`failures.yaml` listing which slices were missing — never silently drop
slices.

## Adapt this section

- `worker_count` — defaults to 4. Tune for your token budget and the
  external API's concurrency limit.
- `slice_assignment_strategy` — `round_robin` is the safe default;
  `size_balanced` requires you to estimate item cost up front;
  `by_label` is useful when item kind matters (bugs vs features) and
  you want a worker specialized per kind (in which case you ARE varying
  worker prompts — see anti-patterns).
- Reducer ranking key — defaults to a worker-emitted `priority_score`
  in `[0,1]`. Swap for your own scoring function.
- Per-worker timeout — defaults to 5 min. If a worker exceeds this, the
  mission proceeds without that slice and logs the gap.

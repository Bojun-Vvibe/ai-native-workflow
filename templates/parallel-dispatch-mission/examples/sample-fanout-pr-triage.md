# Worked example: PR triage fan-out, 12 PRs across 4 workers

Synthetic but representative. Target: a hypothetical OSS repo `acme/widget`
with 12 open PRs. Mission inputs:

```yaml
task: "Triage all currently-open PRs"
target_repo: "acme/widget"
worker_count: 4
slice_strategy: "round_robin"
per_worker_timeout_sec: 300
```

## Step 1 — orchestrator emits `slices.yaml`

```yaml
fanout:
  worker_count: 4
  slice_assignment_strategy: round_robin
  total_items: 12
  truncated: false
slices:
  - id: slice-1
    items: [PR#101, PR#105, PR#109]
  - id: slice-2
    items: [PR#102, PR#106, PR#110]
  - id: slice-3
    items: [PR#103, PR#107, PR#111]
  - id: slice-4
    items: [PR#104, PR#108, PR#112]
```

Wall time: ~8 s. Token cost: small — orchestrator only listed PR
numbers and titles, did not read diffs.

## Step 2 — fan-out: 4 workers run concurrently

Each worker receives one slice. Sample worker output (slice-1):

```yaml
slice_id: slice-1
items:
  - id: PR#101
    status: ok
    summary: "Bump axios 1.6.0 -> 1.7.2; CHANGELOG only, no API changes."
    priority_score: 0.35
    findings:
      - low-risk dep bump, CI green
      - reviewer should glance at lockfile only
  - id: PR#105
    status: ok
    summary: "New /healthz endpoint, no auth, returns 200 + build sha."
    priority_score: 0.78
    findings:
      - exposes build sha — confirm intent
      - missing test for the new route
      - good first-pass candidate for merge after test added
  - id: PR#109
    status: error
    summary: ""
    priority_score: 0.0
    findings: []
    reason_if_error: "PR#109 was closed between orchestrator listing and worker fetch."
```

Wall time: ~95 s for the slowest slice (slice-3, which had a 1200-line
PR). The other three finished in 40–60 s. Serial would have been
~4 × 70 s = ~5 min.

## Step 3 — reducer emits `report.md` + `failures.yaml`

`failures.yaml`:

```yaml
failed_slices: []
```

`report.md` (excerpt):

```markdown
# Triage all currently-open PRs

Workers: 4 / 4
Total items: 12

## Queue (status=ok, sorted by priority_score desc)

| # | item | score | summary |
|---|---|---|---|
| 1 | PR#107 | 0.91 | "Fix race in connection pool — has repro test." |
| 2 | PR#103 | 0.84 | "Migrate logger to structured JSON; touches 14 files." |
| 3 | PR#105 | 0.78 | "New /healthz endpoint, no auth, returns 200 + build sha." |
| 4 | PR#110 | 0.66 | "Docs: clarify retry semantics in README." |
| ...
| 11 | PR#101 | 0.35 | "Bump axios 1.6.0 -> 1.7.2; CHANGELOG only." |

## Errors

| item | reason |
|---|---|
| PR#109 | PR was closed between orchestrator listing and worker fetch. |

## Notes

- Slices missing: none
```

## What this run shows

- **Wall-time win:** ~95 s parallel vs ~5 min serial, on a small batch.
  The win grows with batch size.
- **Reducer is mechanical:** it did not re-rank PR#107 above PR#103
  based on judgment; it sorted by the workers' `priority_score` values.
- **Graceful gap handling:** PR#109 closed mid-run. Worker emitted
  `status: error`; reducer surfaced it in the Errors section instead of
  silently dropping it.
- **No cross-worker coupling:** each `worker-slice-N.yaml` was produced
  in isolation. Re-running just slice-3 would not change slices 1, 2, 4.

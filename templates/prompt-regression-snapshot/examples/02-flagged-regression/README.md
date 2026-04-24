# Example 02 — flagged regression

## Setup

Three fixtures, same shape as example 01. The difference:

- `001-extract-user` — `v1` and `v2` outputs identical → MATCH.
- `002-summarise-pr` — `v2` rewords the summary. Same meaning,
  different prose → CHANGED.
- `003-classify-intent` — `v1` and `v2` identical → MATCH.

This simulates a prompt change that altered summarisation style
on one case. The eval rubric ("does it summarise?") would still
pass — but the **observable output** changed, which is what
snapshots detect.

## Bootstrap

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v1 \
    run --write-new
```

## Run with v2

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v2 \
    run --strict
```

Expected output (abbreviated):

```
Cases: 3  MATCH=2  CHANGED=1  NEW=0  MISSING=0

  MATCH    001-extract-user
! CHANGED  002-summarise-pr
        --- 002-summarise-pr.snapshot
        +++ 002-summarise-pr.new
        @@ -1 +1 @@
        -Refactors token-bucket implementation; no behaviour change.
        +This PR refactors the token bucket. There should be no behaviour change at runtime.
  MATCH    003-classify-intent
```

Exit code: `1`. CI fails.

## Reviewer's decision

Two paths:

### Path A — intentional improvement

The reviewer prefers the new wording. They approve:

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v2 \
    approve 002-summarise-pr
```

The snapshot file on disk is updated. Re-run is now green:

```sh
python3 ../../bin/snapshot.py \
    --fixtures fixtures --snapshots snapshots --prompt-sha v2 \
    run --strict
# exit 0
```

The reviewer commits both the prompt change and the new
snapshot in one PR. CI passes.

### Path B — unintentional regression

The reviewer thinks the new wording is worse. They roll back
the prompt change. Re-run goes green without touching the
snapshot.

## What this example demonstrates

- Snapshots catch **prose-level** behavioural changes that
  rubric-based evals routinely miss (the rubric passed; the
  output changed).
- The diff is in the report, no separate inspection step
  needed.
- Approval is a single command. Rollback is also a single
  command (revert the prompt change, do not touch snapshots).
- CI gating via `--strict` is the forcing function. Without
  it, the regression goes silent until a customer notices.

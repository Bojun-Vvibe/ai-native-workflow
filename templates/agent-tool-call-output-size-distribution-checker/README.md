# agent-tool-call-output-size-distribution-checker

Pure stdlib auditor for *output-size anomalies* across a sequence
of agent tool calls. The agent calls the same tool many times,
each call returns some bytes, and most pathologies (silent
truncation at a round byte cap, runaway result blowing the
context window, paginator quietly cooling to nothing, a stub
returning a fixed-shape error envelope) show up first as a shift
in the **size distribution per tool**, not in the content.

This template ignores content entirely. It groups calls by tool
name, computes a robust median + MAD per tool, and emits one
finding per anomalous call.

Six finding classes:

- **`empty_output`** — `output_bytes == 0`. Almost always a
  silent error that the agent then "summarizes" as if it were
  real data.
- **`size_outlier_high`** — `output_bytes > median + 6*MAD` for
  this tool. Likely runaway result, OOM risk, or context blowup
  on the next turn.
- **`size_outlier_low`** — `output_bytes < median - 6*MAD` AND
  the tool's median is at least 64 bytes (so we don't fire on
  small-by-design tools like `ping`). Likely truncation or
  partial failure.
- **`size_at_round_cap`** — `output_bytes` is within 1% of a
  common cap (1024, 2048, 4096, 8192, 16384, 32768, 65536,
  131072). Strong signal the upstream tool silently truncated at
  a byte limit. Worth firing even when a single call is on the
  cap, because this is exactly the failure mode that does not
  show up as an outlier when *every* call is capped.
- **`size_run_monotone_decay`** — three or more consecutive calls
  of the same tool where each output is strictly smaller than the
  previous AND the last is < 50% of the first. Common when an
  upstream cache is cooling, a paginator is advancing past real
  data, or a quota is throttling the response.
- **`size_variance_collapse`** — the tool was called >= 5 times
  and ALL outputs are identical to the byte. Either the tool is
  returning a fixed-shape error envelope (think a 404 JSON body)
  or a stub got left in the loop.

## When to use

- CI assertion on a captured trace: "for tool `search`, no call
  may sit on a round byte cap." Catches the case where a search
  backend was upgraded to a 4096-byte response cap and the agent
  has been quietly dropping results for a week.
- Forensic pass on a degraded agent run: was the regression in
  the model (it stopped asking for enough), in the tool (it
  started returning less), or somewhere in between?
- Pre-merge gate on a tool wrapper change: re-run yesterday's
  trace, confirm no new `size_variance_collapse` shows up, which
  would indicate the wrapper is now returning a constant error
  envelope instead of propagating real data.

## When NOT to use

- This is **not** a content validator. A tool returning 4096
  bytes of garbage will pass everything except `size_at_round_cap`.
  Pair with a content-shape checker.
- Per-tool rules need at least a handful of calls to be useful.
  If a tool fires twice in the trace, only the round-cap and
  empty-output checks meaningfully apply; the distribution-based
  checks degenerate.
- MAD is robust but not magic. A tool whose true distribution is
  bimodal (e.g., cached vs uncached) will surface the
  less-common mode as outliers. Tune `MAD_K` upward, or split
  the trace by upstream cache status before checking.

## Worked example

Input fixture `examples/trace.jsonl` contains 20 tool calls
across four tools: a `search` tool with one capped response, one
empty response, and one runaway; a `fetch_page` tool with a
classic four-call decay run; a `ping` tool that returns the same
42 bytes five times in a row; and a `summarize` tool with one
truncated reply.

Run:

```
python3 checker.py examples/trace.jsonl
```

Verbatim stdout:

```
{"call_index": 6, "detail": "run_len=4 first_bytes=12000 last_bytes=1500 last_call_index=9", "kind": "size_run_monotone_decay", "tool": "fetch_page"}
{"call_index": 10, "detail": "calls=5 bytes=42", "kind": "size_variance_collapse", "tool": "ping"}
{"call_index": 2, "detail": "bytes=4096 cap=4096", "kind": "size_at_round_cap", "tool": "search"}
{"call_index": 4, "detail": "output_bytes==0", "kind": "empty_output", "tool": "search"}
{"call_index": 5, "detail": "bytes=99000 median=4175 mad=142 threshold>5027", "kind": "size_outlier_high", "tool": "search"}
{"call_index": 19, "detail": "bytes=12 median=800 mad=10 threshold<740", "kind": "size_outlier_low", "tool": "summarize"}
```

All six finding classes are exercised by this fixture.

## Schema

Each input line must be a JSON object with at least:

- `call_index` (int)
- `tool` (str)
- `output_bytes` (int, >= 0)

Extra keys are ignored. Lines may arrive out of order; the
checker re-sorts within each tool by `call_index` before applying
the run-decay rule.

Each output line is a JSON object with:

- `tool` (str)
- `call_index` (int) — the offending call (or first call of a
  decaying run, or first call of a variance-collapsed sequence)
- `kind` (str) — one of the six classes above
- `detail` (str) — human-readable details, stable enough to
  diff across runs

## Exit code

Always 0. This is a *reporter*. If you want a hard gate, pipe
into `jq` and check for an empty result.

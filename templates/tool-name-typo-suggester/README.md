# tool-name-typo-suggester

Pure stdlib detector + suggester that turns "agent emitted an unknown tool name" from a dead-end "tool not found" into a structured `(verdict, best, distance, runners_up, reason)` so the host can surface the right correction to the agent on the next turn — or auto-correct under explicit policy — without burning a retry on the same typo.

## Problem

When an agent in autonomous mode emits a tool call, four typo classes show up empirically:

| Class | Example | Edit distance |
|---|---|---|
| substitution | `read_fle` → `read_file` | 1 |
| insertion    | `read_files` → `read_file` (or vice-versa) | 1 |
| deletion     | `read_fil` → `read_file` | 1 |
| transposition | `raed_file` → `read_file` | 1 |

A naive host responds `error: tool_not_found` and the agent simply retries the same typo on the next turn — burning a model call, a tool-call slot, and (under retry-envelope) an idempotency key. Worse: if "tool_not_found" is hard-classified as `do_not_retry` upstream, the mission gives up on what was a one-character typo.

## When to use

- Any host that dispatches agent-generated tool names against a registry.
- Pair with `tool-permission-grant-envelope` (run typo-suggester *first*, then permission gate the resolved name) so a `read_fil` typo doesn't surface as a misleading `no_grant` for `read_fil`.
- Pair with `agent-handoff-message-validator` if `tool_name` is one of the validated payload fields — typo-suggester runs as a sub-check rather than the validator failing the whole handoff over a one-character drift.

## Design

- **Normalization**: case-fold + strip everything outside `[a-z0-9_]`. So `READ_FILE` → `read_file`. Keeps the suggester deterministic and order-independent.
- **Distance**: Damerau-Levenshtein (1-cost adjacent transposition) so `raed_file` → `read_file` is distance 1 — the same as a single substitution. Plain Levenshtein would charge it 2 and the threshold would miss real typos.
- **Verdict surface** (4 outcomes):
  - `exact` — registry hit verbatim (after normalization).
  - `suggestion` — single best candidate within `max_distance` (default 2) AND beats the runner-up by `tie_break_margin` (default 1). Reason is `clear_winner` or `single_candidate`.
  - `unknown` with `runners_up` populated — two or more candidates tied within `tie_break_margin` (`reason="ambiguous"`). Surface them all to the agent rather than guess wrong.
  - `unknown` with `runners_up=[]` — no candidate within `max_distance` (`reason="no_candidate_within_distance"`).
- **Construction-time validation**: registry collisions after normalization (`read_file` and `Read_File`) raise at `__init__`, not silently on first lookup. A registry that collapses two distinct tools onto one key has lost the ability to disambiguate — fail loudly.
- **Stable ordering**: candidates within distance are returned distance-asc, then alphabetical. Two consecutive runs of the same input produce byte-identical `runners_up` for diffability.
- **Empty / non-string input**: `verdict="unknown"` with `reason="no_candidate_within_distance"` — never raises, never crashes the dispatch path.

## Files

- `suggester.py` — `TypoSuggester(registry, max_distance=2, tie_break_margin=1)` with `.suggest(name) -> Suggestion`. Stdlib only (`re`, `dataclasses`).
- `example.py` — six-scenario worked example (exact, substitution, transposition, ambiguous, unknown, registry-collision rejection) + invariants + a host-wiring demo that emits the JSON the orchestrator should send back.

## Worked example output

Captured by running `python3 templates/tool-name-typo-suggester/example.py`:

```
registry: ['delete_file', 'list_dir', 'read_file', 'read_files', 'run_shell', 'search_grep', 'write_file']

--- 1. exact ---
input:    'read_file'
verdict:  exact
best:     'read_file'
distance: 0
runners:  []
reason:   exact_match

--- 2. substitution ---
input:    'read_fle'
verdict:  suggestion
best:     'read_file'
distance: 1
runners:  [('read_files', 2)]
reason:   clear_winner

--- 3. transposition ---
input:    'raed_file'
verdict:  suggestion
best:     'read_file'
distance: 1
runners:  [('read_files', 2)]
reason:   clear_winner

--- 4. ambiguous ---
input:    'read_filex'
verdict:  unknown
best:     None
distance: None
runners:  [('read_file', 1), ('read_files', 1)]
reason:   ambiguous

--- 5. unknown ---
input:    'launch_nukes'
verdict:  unknown
best:     None
distance: None
runners:  []
reason:   no_candidate_within_distance

--- 6. registry collision rejected ---
raised ValueError as expected: registry collision after normalization: 'read_file' vs 'Read_File'

--- invariants ---
case-fold exact match: 'read_file' (passes)
empty input -> verdict=unknown (passes)

--- host wiring demo ---
{
  "error": "unknown_tool",
  "received": "read_fle",
  "suggestion": "read_file",
  "distance": 1,
  "hint": "Did you mean 'read_file'?"
}
```

Note scenario 4: input `read_filex` is exactly distance 1 from BOTH `read_file` (delete `x`) AND `read_files` (substitute `x→s`). The suggester refuses to guess and surfaces both — the orchestrator's next turn can either show both to the agent ("did you mean read_file or read_files?") or, under a strict-correction policy, deny the call. A naive "pick the alphabetically-first" tiebreak would silently route `read_filex` to `read_file` and the bug would never appear in the mission log.

## Composes with

- `tool-permission-grant-envelope` — resolve typos *before* the grant check so denial reasons are accurate (`tool_not_in_grant: read_file`, not `tool_not_in_grant: read_fil`).
- `structured-error-taxonomy` — `verdict="unknown"` classifies as `bad_input / do_not_retry / attribution=agent`. The agent caused the typo; retrying the identical call won't fix it.
- `agent-decision-log-format` — log every non-exact verdict (`reason`, `received`, `best`, `distance`) so a sudden spike in `clear_winner` corrections is the signal that a model swap regressed tool-name fidelity.

# Examples

Three worked examples of the four-question checklist firing on
real-shaped diffs. Each example contains:

- `diff.patch` — a synthetic but realistic unified diff that
  triggers the bug shape.
- `finding.md` — the structured output the agent prompt would
  produce for that diff (or that a human reviewer running the
  checklist by hand would write).

The diffs are synthetic so they can be checked in safely (no
upstream attribution, no copyrighted hunks), but each is modeled on
a real PR review the source post draws from.

| Example | Question fired | Bug shape |
|---|---|---|
| `01-streaming-decode-loop/` | Question 1 | Early-return loop drops the second non-synthetic block in a streaming decoder. |
| `02-completion-event-race/` | Question 2 | Wrong-sync event closes the listener before the slow second signal arrives. |
| `03-provider-role-translator/` | Question 3 | Non-portable enum default-passthrough leaks a provider-specific role through to internal code. |

A fourth example (drifted second constructor) is omitted here
because that shape requires reading two separated regions of a
file, which doesn't render well in a single short diff. The
`failure-mode-catalog` template's "Lost Diff" section has a worked
example for it.

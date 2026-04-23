# Trailer keys (canonical)

Git trailers are `Key: value` lines in the **last** paragraph of a
commit message, separated from the body by a blank line. This file
is the canonical allow-list. The `commit-msg` hook rejects unknown
keys.

## Allowed keys

| Key                | Value format                          | Notes |
|--------------------|---------------------------------------|-------|
| `Co-Authored-By`   | `Name <email>`                        | One per additional contributor. AI agents use a stable invalid email like `agent-implementer <agent@example.invalid>`. |
| `Mission-Id`       | `M-YYYY-MM-DD-Wnn` or `M-<slug>`      | Mission this commit belongs to. Optional for human-only commits. |
| `Model`            | provider's exact model id             | e.g. `claude-opus-4.7`, `gpt-5-mini`. Lowercase, hyphenated. |
| `Tokens-In`        | integer                               | Cumulative input tokens for this commit's work. Includes cache reads. |
| `Tokens-Out`       | integer                               | Cumulative output tokens for this commit's work. |
| `Cache-Hit-Rate`   | float in `[0,1]`, three decimals max  | `cache_read / (cache_read + fresh_input)`. |
| `Signed-off-by`    | `Name <email>`                        | DCO sign-off. Standard Linux convention. |

## Forbidden / rejected keys

- Any key not in the table above. Rejected by `commit-msg` hook.
- Keys with mixed case (`Tokens-in`). Use the exact case above.
- Keys with underscores (`tokens_in`). Use hyphens.

## Multi-trailer ordering

When multiple trailers appear, the recommended order is:

1. `Co-Authored-By` (one per author)
2. `Mission-Id`
3. `Model`
4. `Tokens-In`
5. `Tokens-Out`
6. `Cache-Hit-Rate`
7. `Signed-off-by` (last, by convention)

`git interpret-trailers --sort` will preserve insertion order;
ordering matters for diff readability, not for parsing.

## Why these specific keys

- **`Co-Authored-By`**: works on GitHub, GitLab, and Gitea today;
  shows the additional author in the UI.
- **`Mission-Id`**: lets you `git log --grep "Mission-Id: M-2026-04"`
  to see one mission's commit set.
- **`Model`**: a regression bisect can answer "which model wrote
  this?" without leaving git.
- **`Tokens-In/Out` + `Cache-Hit-Rate`**: enough to compute cost
  per commit at report time, without pinning prices into the
  commit itself (prices change).

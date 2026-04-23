# FM-06 — Cross-repo Blindness

**Severity:** dangerous
**First observed:** any multi-repo workspace
**Frequency in our ops:** weekly when working across repos

## Diagnosis

The agent searches one repo, doesn't find a symbol, and concludes
it doesn't exist. It then writes a duplicate, or makes a change
that breaks consumers in sibling repos it never opened.
Identifier renames are the sharpest version: the agent confidently
renames every site in the repo it can see and ships a PR; the
sibling repos break at compile-time the moment they pick up the
new package.

## Observable symptoms

- Agent declares an identifier "undefined" or "doesn't exist"
  while another repo in the workspace clearly defines or imports
  it.
- Cross-repo CI fails after a "completed" rename.
- Agent writes a helper that already exists, identically, in a
  sibling repo.
- Reviewer comments like "what about repo X?" on every PR.

## Mitigations

1. **Primary** — use
   [`multi-repo-monorepo-bridge`](../../multi-repo-monorepo-bridge/)
   so the agent searches the whole workspace by default.
2. **Secondary** — for any rename or signature change, require a
   `bridge-search` of the new and old name as a final
   verification step before commit. Empty-result on the old name
   is the gate.

## Related

FM-10 (Confident Fabrication — "this function doesn't exist" is
often a fabrication that bridge-search would have refuted).

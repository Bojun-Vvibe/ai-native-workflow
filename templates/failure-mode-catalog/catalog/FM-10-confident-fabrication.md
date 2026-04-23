# FM-10 — Confident Fabrication

**Severity:** dangerous
**First observed:** intrinsic to LLMs
**Frequency in our ops:** weekly

## Diagnosis

The agent makes a confident, specific, plausible claim about the
codebase that is false. Examples: "this function is defined in
`src/utils.py`" (it isn't), "the test suite covers this case"
(it doesn't), "the upstream library handles this internally"
(it doesn't). The claim is the kind a careful human would make
after checking; the agent makes it without checking.

This is the most dangerous failure mode in this catalog because
the agent's prose around the claim is well-structured and
referenced — it sounds like the result of investigation. The only
defense is verification.

## Observable symptoms

- Specific file paths or function names mentioned without a
  corresponding tool call to read them.
- Claims about external libraries' behavior with no doc lookup.
- Quotes from "the test suite" that don't appear in any test file.
- Reviewer (human or agent) finds a claim is false on a 30-second
  grep.

## Mitigations

1. **Primary** — pair the implementer with a different reviewer
   ([`multi-agent-implement-review-loop`](../../multi-agent-implement-review-loop/)).
   The reviewer's job description must include "grep every file
   path the implementer references."
2. **Secondary** — for any agent-generated PR description,
   pre-process it through a "grep the claim" step that flags
   every file/function reference and verifies it exists.

## Related

FM-04 (Premature Convergence often produces the fabrications),
FM-06 (Cross-repo Blindness is fabrication's twin — "this
doesn't exist" rather than "this exists here").

### Question 1: every loop with a filter — does it return on the first match?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

### Question 2: every "we're done" signal — is there a second signal that could lag?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

### Question 3: every translator — what does the default branch do?

**Applies to:** `src/providers/role_translator.py:12-29`

**Pattern observed:** Two translators with default-passthrough
branches that leak source values into the destination enum.

The Anthropic branch uses `mapping.get(role, role)` — if Anthropic
introduces a new role tomorrow (e.g. `"system"` becomes a
first-class role with different semantics, or a new `"tool_use"`
role appears), it will pass through as-is. The internal enum is
declared as a closed set `INTERNAL_ROLES = {"user", "assistant",
"system", "tool"}`. Anthropic-side `"tool_use"` is not in that
set; if it ever arrives, downstream code that switches on
`INTERNAL_ROLES` will hit an unhandled case.

The OpenAI branch's bare `return role` after the `function ->
tool` rewrite has the same shape: it assumes OpenAI's role
domain is a subset of the internal domain forever. The OpenAI
"developer" role (introduced for the o-series models) is not in
`INTERNAL_ROLES` and would silently pass through.

**Bug-shape risk:** high

**Counter-question for the author:** What does this function
return today if Anthropic emits a role of `"tool_use"` or OpenAI
emits a role of `"developer"`? Is there a downstream consumer
that does `assert role in INTERNAL_ROLES` or that switches on
the internal role and would crash on an unmapped value? Should
the default branch raise `ValueError` instead of passing
through?

**Suggested test:** Parametrized test with the cross-product of
`{provider: anthropic | openai} × {role: every_known_role +
unknown_role}`. Assert that every (provider, role) either
produces a value in `INTERNAL_ROLES` or raises a clearly named
exception. The current implementation will fail for any new
provider role that isn't explicitly mapped.

---

### Question 4: every constructor — are there other constructors that share concerns?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

SUMMARY: 1/4 questions fired (high: 1, medium: 0, low: 0)

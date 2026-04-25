# `prompt-template-versioner`

Named prompt-template registry with semver-style version resolution
and **explicit fallback chains**. Pure stdlib, deterministic.

## Distinct from `prompt-version-pinning-manifest`

- [`prompt-version-pinning-manifest`](../prompt-version-pinning-manifest/)
  *pins* a single tuple by SHA-256 fingerprint and fails CI on drift.
  It is a **lockfile**.
- This template *resolves* a `(name, version_spec)` request to the best
  available concrete version and renders it. It is the **registry**
  that produces the artifact a manifest then pins.

The two compose: render via this versioner, fingerprint with the
manifest, pin the result.

## Why this exists

Two failure modes show up the moment a prompt has a second author:

1. **`latest` drifts across breaking boundaries.** Someone registers
   `code-review` v2.0.0 with a JSON output contract. Every caller that
   was using `"latest"` instantly stops parsing the response. The
   version system gave you no warning because `"latest"` was never a
   real pin — it was a coin flip whose result depended on registration
   order.
2. **Exact pins rot in production.** A caller pinned to `1.1.0` misses
   the `1.1.1` patch that fixes a citation-format bug. Patches were
   meant to be free.

The versioner gives callers four resolution shapes — exact, minor,
major, latest — plus an **explicit fallback chain** that lets a caller
declare "I want 3.x; if nothing in 3.x is registered, fall back to 2.x;
**never** silently drop to 1.x." The chain is reviewable in the diff.
`"latest"` and silent-major-drop are no longer the only options.

## Contract

### Specifiers

| Spec        | Meaning                                  | Misses raise |
|-------------|------------------------------------------|---|
| `"1.4.2"`   | exact pin                                | yes |
| `"1.4"`     | latest patch within MAJOR.MINOR          | yes |
| `"1"`       | latest minor.patch within MAJOR          | yes |
| `"latest"`  | absolute latest registered version       | yes (only if name unknown) |

### Fallback chain

`resolve_with_fallback(reg, name, ["3", "2"])` tries `"3"` then `"2"`,
returns the first that resolves, and reports `fell_back_from=["3"]`
in the `Resolution` so callers can log "we wanted 3.x, got 2.x".

If no spec in the chain resolves, **`TemplateNotFound` raises**. This
is the load-bearing safety property: a caller that says "3.x or 2.x"
will never get a 1.x prompt by accident, even if 1.x is the only thing
in the registry.

### Rendering

Templates use `string.Template` syntax (`$var`, `${var}`). Missing
variables **raise `KeyError`** loudly. A template typo never silently
emits an empty string and degrades the prompt — the orchestrator finds
out at render time.

### Registry semantics

- `register(name, version, body)` — duplicate `(name, version)` raises.
  Templates are immutable once registered.
- In-memory by design. Production deployments load the registry from a
  directory of files at process startup and never mutate at runtime, so
  resolution is reproducible across replicas.

## Worked example output

`python3 worked_example.py` prints the following (captured verbatim):

```
================================================================
1. Registered templates
================================================================
  code-review     versions: ['1.0.0', '1.1.0', '1.1.1', '2.0.0']
  summarize       versions: ['0.3.0']

================================================================
2. Exact pin: code-review 1.1.0
================================================================
  matched: 1.1.0
  body:    'Review this diff and report issues. Cite line numbers.\n$diff'

================================================================
3. Floating minor: code-review 1.1 (latest patch)
================================================================
  matched: 1.1.1  (expected 1.1.1 — latest patch in 1.1)

================================================================
4. Floating major: code-review 1 (latest 1.x)
================================================================
  matched: 1.1.1  (expected 1.1.1 — latest in 1.x, NOT 2.0.0)

================================================================
5. Absolute latest
================================================================
  matched: 2.0.0  (expected 2.0.0)

================================================================
6. Fallback chain: prefer 3.x, accept 2.x, refuse 1.x or older
================================================================
  matched: 2.0.0
  fell_back_from: ['3']  (3.x not registered, 2.x found)

================================================================
7. Fallback chain that refuses to silently drop majors
================================================================
  raised: TemplateNotFound: no version of 'code-review' matched any spec in chain ['5', '4']

================================================================
8. Render: missing variable raises (no silent empty string)
================================================================
  raised: KeyError: 'diff'  (template typo never silently emits an empty string)

================================================================
9. Render: success
================================================================
Review this diff and report issues. Cite line numbers as `file:line`.
--- a/auth.py
+++ b/auth.py
@@ -1 +1 @@

================================================================
10. Unknown template
================================================================
  raised: TemplateNotFound: no template registered: 'does-not-exist'
```

Reading the sections in order:

- §3 confirms the **patch-floats-up** property: a caller asking for
  `"1.1"` automatically picks up `1.1.1`'s citation-format fix without
  re-deploying.
- §4 confirms the **major-does-not-cross** property: a caller asking
  for `"1"` gets `1.1.1`, **not** `2.0.0`. The breaking JSON-output
  change in `2.0.0` is invisible to `"1"`-pinned callers.
- §5 vs §4 illustrates exactly why `"latest"` is dangerous and why
  major-spec is the safer default for callers that want patches but
  not breakage.
- §6 is the everyday fallback case: a caller targets the future major
  but the registry hasn't caught up, so the chain backs off one step
  and reports the back-off in `fell_back_from` so an operator can grep
  for "still on the old major".
- §7 is the safety property: a chain whose floor is `"4"` will refuse
  rather than silently land on a stale `1.x` or `2.x` template.
- §8 demonstrates the loud-failure render contract — a template typo
  in the variables dict surfaces at render time, not at model-output
  time.

## Files

- [`versioner.py`](versioner.py) — `TemplateRegistry`, `resolve`,
  `resolve_with_fallback`, `Resolution.render`.
- [`worked_example.py`](worked_example.py) — runnable end-to-end
  demonstration. Output above is captured from this script.

## Operating notes

- **Never mutate the registry at runtime.** A new template version is
  a new release. Mutating mid-process makes resolution non-reproducible
  across replicas and breaks any downstream fingerprint pin.
- **Prefer major or major.minor specs over `"latest"`.** `"latest"` is
  only safe for ad-hoc scripts where breaking the contract is fine.
- **Compose with the manifest.** Resolve here, then fingerprint the
  rendered tuple with
  [`prompt-version-pinning-manifest`](../prompt-version-pinning-manifest/)
  so CI catches the case where the registry was edited without bumping
  the version.
- **Fallback chains should be reviewable.** A chain that drops more
  than one major is a code smell — surface it in code review, not at
  3am during an incident.

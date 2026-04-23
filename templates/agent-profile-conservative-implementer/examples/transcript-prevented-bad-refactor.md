# Transcript: profile prevented a bad refactor

**Scenario**: a small Node service repository. The user wants to add a feature flag
to gate a new endpoint behind an environment variable. The existing config layer
is a hand-rolled `process.env` lookup scattered across handlers — historically
ugly, but stable and well-tested.

**Without this profile**, a typical agent would:

1. Notice the scattered `process.env` reads.
2. Decide that "while I'm here" it should introduce a `config.ts` module.
3. Migrate every handler to import from `config.ts`.
4. Hand back a 600-line diff that includes the requested feature flag plus a
   refactor of every handler in the service.

That diff gets rejected on review. The user reprompts, the agent partly rolls
back, the result is messy, the human reviewer is annoyed, and an hour is gone.

**With this profile loaded**, the session looks like this:

---

## Session

```
[user] Add a feature flag NEW_ENDPOINT_ENABLED that gates the /v2/items
       endpoint. If unset or "false", return 404 from that endpoint.

[agent]
[Conservative Implementer profile loaded]
- Diff cap: 100 + 100 LoC per turn (will ask before exceeding).
- No drive-by refactors, renames, reformatting, or dependency additions.
- Assumptions will be surfaced in a `## Assumptions` section of each response.

I'll add the gate inside the existing /v2/items handler, reading the env var
at request time using the same pattern as the surrounding handlers.

## What I changed
Added an early-return 404 in the /v2/items handler when NEW_ENDPOINT_ENABLED
is unset or the literal string "false". Used the same direct process.env
read pattern as the other handlers in this file.

## Files touched
- src/routes/items.ts (+8, -0)

## Assumptions
- "Unset" means env var absent OR empty string (matches what the existing
  AUTH_BYPASS flag does in the same file at line 14).
- The 404 response body should match the framework default; you didn't
  specify a custom body. Tell me if you want one.

## Out of scope (noticed but did not change)
- Every handler in this service reads process.env directly. There's a clear
  argument for centralizing into a config module, but that's a separate
  refactor with its own review surface and its own test impact. Not touching
  it as part of a feature flag request.
- The /v2/items handler has no unit test today. I did not add one because
  you didn't ask, but a single test for "flag off → 404, flag on → 200"
  would lock in this behavior.

## Suggested follow-ups
- Open a separate request for "centralize env var access" if you want that
  refactor. Easier to review on its own.
- Open a separate request to add the missing test for the flag behavior.

[user] Add the test.

[agent]
## What I changed
Added a single test file covering both branches of the new flag.

## Files touched
- test/routes/items.test.ts (+34, -0)

## Assumptions
- Reused the same test framework (vitest) and helper imports as the
  neighboring test/routes/auth.test.ts.
- Mocked process.env via vi.stubEnv; this matches how auth.test.ts
  handles env var stubbing.

## Out of scope
None.

## Suggested follow-ups
None — flag and test ship together cleanly.
```

---

## What the profile prevented

- **A 600-line drive-by refactor**, which would have:
  - Forced the reviewer to re-read every handler in the service.
  - Tangled the feature flag with the refactor in `git blame` forever.
  - Likely broken at least one handler that depended on a subtle env-var quirk.
- **A new dependency** (some agents reach for `dotenv` or `config` package without asking).
- **Renamed env vars** to fit a "consistent" scheme — silently breaking deployments.

## What the profile cost

- One extra prompt-response round-trip (the user had to ask for the test
  separately). This is the price of scope discipline. It's small.

## Generalizable lesson

The profile didn't make the agent smarter. It made the agent *narrower*. On
unfamiliar codebases that's almost always the right tradeoff: the human
reviewer can request more, but they can't easily request less.

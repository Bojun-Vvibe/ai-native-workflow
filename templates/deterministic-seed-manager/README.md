# deterministic-seed-manager

Pure stdlib seed-derivation primitive for agent runs that need to be
reproducible without coupling unrelated steps.

## Why

"Just pass `seed=42` everywhere" is the bug:

- A run that reuses the **same** seed across every step couples step 7's
  output to the noise sample chosen for step 1. Resampling step 1
  reshuffles every downstream step, so an A/B comparison of two prompt
  versions never converges.
- Two parallel workers in a fan-out with the same seed produce
  **correlated** noise — they fail in the same way for the same reason
  and the orchestrator thinks the failure is "real" instead of an
  artifact of its own seeding.
- Resetting `random.seed(...)` mutates the global RNG and is the most
  common source of "passes in isolation, fails in CI" bugs.

The fix is **seed derivation**: pick one root seed for the whole
mission, then derive a fresh per-`(step_id, attempt, worker_id)` seed
from it via a stable hash. Replays of the same `(root, step, attempt,
worker)` are byte-stable; sibling derivations are independent.

## Interface

- `SeedManager.from_random()` — mint a brand-new 256-bit root from
  `secrets.token_hex(32)`. Use for new mission starts.
- `SeedManager.from_env("MISSION_ROOT_SEED")` — read the root from an
  env var. Production replay path.
- `SeedManager.from_hex(hex64)` — replay path from a saved trace.
- `sm.derive(step_id=..., attempt=..., worker_id="") -> DerivedSeed`
  with `bytes32`, `int64`, and `hex` fields.
- `sm.random_for(step_id=..., attempt=..., worker_id="") ->
  random.Random` — fresh RNG, never touches the global one.

## Design rules

1. Root is a **256-bit hex string** (64 chars). `from_hex` validates
   length and hex-ness — a half-typed env var fails loudly, not
   silently with a different root.
2. Derivation uses `hashlib.blake2b(key=root_bytes, person=...)` over
   a **canonical JSON** serialization of `(step_id, attempt,
   worker_id)`. Canonical means dict-order-independent, whitespace-free
   bytes — replay across Python versions / OSes is byte-stable.
3. `attempt` is **required**, not defaulted. A retry of step 7 with the
   same `attempt` reproduces the original seed (idempotency); a retry
   under a new `attempt` value gets a different seed (so two retries
   don't sample the same noise and fail for the same reason).
4. `step_id` must be **non-empty**. Empty would silently collide every
   derivation across the mission.
5. `random_for` returns a **fresh `random.Random`** instance. It
   never calls `random.seed(...)`. Two callers in different threads
   can pull RNGs concurrently without interference.
6. `bool` is rejected for `attempt` even though `isinstance(True, int)`
   — silent `True → 1` would conflate the "first retry" of step 7 with
   the (much rarer) caller bug of passing a flag where an int was
   expected.

## When to use

- LLM calls with non-zero temperature where you want
  reproducibility for replay / regression testing.
- Sampling / shuffling inside agent steps (data subsampling, A/B
  bucketing, retry-jitter where you also want determinism on replay).
- Any tool call whose output is sensitive to a seed (Monte Carlo
  estimation, fuzzing, synthetic-data generation).

## When NOT to use

- For cryptographic secrets — derive a real KDF (HKDF / scrypt /
  argon2) for keys, not this. This is a *replay* primitive, not a
  *secrecy* primitive (the root is in the trace).
- For idempotency keys — use `tool-call-retry-envelope`'s
  `idempotency_key` instead; that contract is about *side-effect
  identity*, not *noise identity*.
- For `random.SystemRandom` substitutes — `random_for` returns the
  Mersenne-Twister `random.Random`, which is non-cryptographic by
  design (and that is what reproducibility wants).

## Composes with

- `agent-checkpoint-resume` — record `derive(...).hex` in the
  `step_begin` record. On resume, re-derive and assert byte-equality
  before replaying — catches "I changed the root since this checkpoint
  was written" silently.
- `prompt-fingerprinting` — feed `derive(...).hex` into the prompt
  package as `noise_seed` so the fingerprint changes when the noise
  changes (otherwise a re-seeded run looks identical to the cache layer).
- `tool-call-replay-log` — a replay reads the original root from the
  log, reconstructs the SeedManager, and reproduces every per-step
  RNG byte-identically.
- `parallel-dispatch-mission` — pass `worker_id=worker.name` into
  `derive(...)` so the N parallel workers in a fan-out get N
  independent seeds without the orchestrator hand-picking them.

## Run

```
python3 worked_example.py
```

## Example output

```
======================================================================
deterministic-seed-manager :: worked example
======================================================================

root_hex (16-char prefix) : 0123456789abcdef...
root_hex length           : 64 chars

[plan/attempt=0 (call 1)]
  hex_prefix : 71febccd897683da...
  int64      : 8214210361330926554
  bytes32    : 71febccd897683da... (32 bytes)

[plan/attempt=0 (call 2)]
  hex_prefix : 71febccd897683da...
  int64      : 8214210361330926554
  bytes32    : 71febccd897683da... (32 bytes)

  property: idempotent under same inputs ......... OK

[implement/attempt=0]
  hex_prefix : eeb0c8bfc71585f4...
  int64      : 17199467702932309492
  bytes32    : eeb0c8bfc71585f4... (32 bytes)

  property: sibling steps are independent ........ OK

[plan/attempt=1 (retry)]
  hex_prefix : 58dae0c5ac268f07...
  int64      : 6402676959861968647
  bytes32    : 58dae0c5ac268f07... (32 bytes)

  property: retry seeds independent of original .. OK

[parallel workers fanout/attempt=0]
  w-0 int64 : 11238810616143163483
  w-1 int64 : 18290185920042300812
  w-2 int64 : 10395537367363637264

  property: distinct workers -> distinct seeds ... OK

[random_for]
  rng_a sequence : [340, 332, 464, 568, 406]
  rng_b sequence : [340, 332, 464, 568, 406]
  rng_a == rng_b : True
  global RNG untouched : True

  property: replay from saved root reproduces .... OK

[malformed_inputs_caught]
  short_root         -> root seed hex must be 64 chars (256 bits), got 9
  nonhex_root        -> root seed is not valid hex: invalid literal for int() with b
  empty_step_id      -> step_id must be a non-empty string
  negative_attempt   -> attempt must be >= 0, got -1
  bool_attempt       -> attempt must be int (not bool), got bool
  env_unset          -> environment variable 'DEFINITELY_NOT_SET_DSM_TEST_VAR' is un

----------------------------------------------------------------------
Invariants:
  derive is idempotent under same inputs              OK
  sibling step_ids derive independent seeds            OK
  retry attempts derive independent seeds              OK
  parallel workers derive independent seeds            OK
  random_for never mutates the global random module    OK
  replay from saved root_hex reproduces byte-identical OK
  6 malformed inputs raise SeedConfigError             OK

DONE.
```

(The hex / int values are byte-stable for the fixed root in the worked
example. A real run via `SeedManager.from_random()` produces a
different root every time but the same per-`(step, attempt, worker)`
properties hold.)

"""End-to-end worked example for deterministic-seed-manager.

Stdlib only. Run:

    python3 worked_example.py
"""

from __future__ import annotations

from seed_manager import (
    DerivedSeed,
    SeedConfigError,
    SeedManager,
)


def banner(s: str) -> None:
    print("=" * 70)
    print(s)
    print("=" * 70)


def show_derived(label: str, ds: DerivedSeed) -> None:
    print(f"[{label}]")
    print(f"  hex_prefix : {ds.hex[:16]}...")
    print(f"  int64      : {ds.int64}")
    print(f"  bytes32    : {ds.bytes32[:8].hex()}... ({len(ds.bytes32)} bytes)")
    print()


def main() -> int:
    banner("deterministic-seed-manager :: worked example")
    print()

    # Use a fixed root so the worked example output is byte-stable.
    # In production, prefer SeedManager.from_random() (new run) or
    # SeedManager.from_env("MISSION_ROOT_SEED") (replay).
    root = "0123456789abcdef" * 4  # 64 hex chars
    sm = SeedManager.from_hex(root)
    print(f"root_hex (16-char prefix) : {sm.root_hex()[:16]}...")
    print(f"root_hex length           : {len(sm.root_hex())} chars")
    print()

    # --- Property 1: idempotent --------------------------------------------
    a1 = sm.derive(step_id="plan", attempt=0)
    a2 = sm.derive(step_id="plan", attempt=0)
    show_derived("plan/attempt=0 (call 1)", a1)
    show_derived("plan/attempt=0 (call 2)", a2)
    assert a1 == a2, "same inputs MUST derive the same seed"
    print("  property: idempotent under same inputs ......... OK")
    print()

    # --- Property 2: different step -> different seed ----------------------
    b = sm.derive(step_id="implement", attempt=0)
    show_derived("implement/attempt=0", b)
    assert b.int64 != a1.int64
    assert b.bytes32 != a1.bytes32
    print("  property: sibling steps are independent ........ OK")
    print()

    # --- Property 3: same step, different attempt -> different seed --------
    a_retry = sm.derive(step_id="plan", attempt=1)
    show_derived("plan/attempt=1 (retry)", a_retry)
    assert a_retry.int64 != a1.int64
    print("  property: retry seeds independent of original .. OK")
    print()

    # --- Property 4: parallel workers don't collide ------------------------
    w0 = sm.derive(step_id="fanout", attempt=0, worker_id="w-0")
    w1 = sm.derive(step_id="fanout", attempt=0, worker_id="w-1")
    w2 = sm.derive(step_id="fanout", attempt=0, worker_id="w-2")
    print(f"[parallel workers fanout/attempt=0]")
    print(f"  w-0 int64 : {w0.int64}")
    print(f"  w-1 int64 : {w1.int64}")
    print(f"  w-2 int64 : {w2.int64}")
    assert w0.int64 != w1.int64 != w2.int64 and w0.int64 != w2.int64
    print()
    print("  property: distinct workers -> distinct seeds ... OK")
    print()

    # --- Property 5: random.Random is fresh, never global ------------------
    import random as _random
    _random.seed(99999)  # set a known global state
    rng_a = sm.random_for(step_id="sample", attempt=0)
    rng_b = sm.random_for(step_id="sample", attempt=0)
    seq_a = [rng_a.randint(0, 1000) for _ in range(5)]
    seq_b = [rng_b.randint(0, 1000) for _ in range(5)]
    # Two RNGs from the same derivation produce identical sequences:
    assert seq_a == seq_b, (seq_a, seq_b)
    # And the global random module's state was NOT consumed:
    global_after = _random.randint(0, 10**9)
    _random.seed(99999)
    global_expected = _random.randint(0, 10**9)
    assert global_after == global_expected, "random_for leaked into global RNG!"
    print(f"[random_for]")
    print(f"  rng_a sequence : {seq_a}")
    print(f"  rng_b sequence : {seq_b}")
    print(f"  rng_a == rng_b : {seq_a == seq_b}")
    print(f"  global RNG untouched : True")
    print()

    # --- Property 6: replay across SeedManager instances -------------------
    sm_replay = SeedManager.from_hex(root)
    a_replay = sm_replay.derive(step_id="plan", attempt=0)
    assert a_replay == a1, "replay from same root MUST match original"
    print("  property: replay from saved root reproduces .... OK")
    print()

    # --- Property 7: malformed inputs raise loudly -------------------------
    caught: list[tuple[str, str]] = []
    try:
        SeedManager.from_hex("too-short")
    except SeedConfigError as e:
        caught.append(("short_root", str(e)[:60]))
    try:
        SeedManager.from_hex("z" * 64)  # not hex
    except SeedConfigError as e:
        caught.append(("nonhex_root", str(e)[:60]))
    try:
        sm.derive(step_id="", attempt=0)
    except SeedConfigError as e:
        caught.append(("empty_step_id", str(e)[:60]))
    try:
        sm.derive(step_id="x", attempt=-1)
    except SeedConfigError as e:
        caught.append(("negative_attempt", str(e)[:60]))
    try:
        sm.derive(step_id="x", attempt=True)  # type: ignore[arg-type]
    except SeedConfigError as e:
        caught.append(("bool_attempt", str(e)[:60]))
    try:
        SeedManager.from_env("DEFINITELY_NOT_SET_DSM_TEST_VAR")
    except SeedConfigError as e:
        caught.append(("env_unset", str(e)[:60]))

    print("[malformed_inputs_caught]")
    for kind, msg in caught:
        print(f"  {kind:18s} -> {msg}")
    print()
    assert len(caught) == 6

    # --- Final summary -----------------------------------------------------
    print("-" * 70)
    print("Invariants:")
    print(f"  derive is idempotent under same inputs              OK")
    print(f"  sibling step_ids derive independent seeds            OK")
    print(f"  retry attempts derive independent seeds              OK")
    print(f"  parallel workers derive independent seeds            OK")
    print(f"  random_for never mutates the global random module    OK")
    print(f"  replay from saved root_hex reproduces byte-identical OK")
    print(f"  6 malformed inputs raise SeedConfigError             OK")
    print()
    print("DONE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

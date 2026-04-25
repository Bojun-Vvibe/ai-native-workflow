"""worked_example.py — four scenarios for the conversation turn pruner.

Run with:
    python3 worked_example.py
"""

from __future__ import annotations

from turn_pruner import Turn, PrunePolicy, prune, DEFAULT_ELISION_MARKER


def _show(label: str, result) -> None:
    print(f"== {label} ==")
    print(f"  kept: {len(result.kept)} turn(s)  dropped: {len(result.dropped)} turn(s)  "
          f"marker_inserted={result.marker_inserted}")
    print(f"  kept_tokens={result.kept_token_count}  dropped_tokens={result.dropped_token_count}")
    print("  kept roles:", [t.role for t in result.kept])
    print("  decisions:")
    for d in result.decisions:
        print(f"    - {d}")


def scenario_short_no_prune_needed() -> None:
    turns = [
        Turn("system", "You are a careful refactoring assistant."),
        Turn("user", "Rename foo to bar across the repo."),
        Turn("assistant", "Done. 14 files updated."),
        Turn("user", "Run the tests."),
        Turn("assistant", "All 312 tests pass."),
    ]
    policy = PrunePolicy(keep_first=2, keep_last=2)
    result = prune(turns, policy)
    _show("short_no_prune_needed", result)
    assert not result.marker_inserted
    assert len(result.kept) == 5


def scenario_long_middle_drop() -> None:
    # 1 system + 12 conversation turns. Keep first 2 + last 3 → drop 7 middle.
    turns = [Turn("system", "You are a meticulous research assistant.")]
    turns.append(Turn("user", "Investigate why the build is flaky on macOS arm64."))
    turns.append(Turn("assistant", "Starting investigation. Reading CI logs."))
    for i in range(7):
        turns.append(Turn("assistant", f"Tool retry attempt {i+1}: still flaky."))
    turns.append(Turn("user", "Skip retries; check the test runner config."))
    turns.append(Turn("assistant", "Found it: parallel=true with a shared tmpdir."))
    turns.append(Turn("user", "Patch please."))
    policy = PrunePolicy(keep_first=2, keep_last=3)
    result = prune(turns, policy)
    _show("long_middle_drop", result)
    assert result.marker_inserted
    assert len(result.dropped) == 7
    # Marker should sit between the head anchors and the tail recents.
    roles = [t.role for t in result.kept]
    # 1 system + 2 head (user, assistant) + marker (system) + 3 tail (user, assistant, user)
    assert roles == ["system", "user", "assistant", "system", "user", "assistant", "user"]


def scenario_pinned_middle_survives() -> None:
    turns = [
        Turn("system", "You are a code reviewer."),
        Turn("user", "Review PR #42."),
        Turn("assistant", "Reading diff..."),
        Turn("tool", "Diff: 142 lines across 7 files"),
        # This middle turn is pinned — load-bearing tool result.
        Turn("tool", "SECURITY SCAN: 1 high finding (hardcoded API key in src/x.py)",
             pinned=True),
        Turn("assistant", "I'll start with the security finding."),
        Turn("assistant", "Reading src/x.py..."),
        Turn("assistant", "Reading src/y.py..."),
        Turn("assistant", "Reading src/z.py..."),
        Turn("user", "What's the verdict?"),
        Turn("assistant", "Block on the API key. The rest is fine."),
    ]
    policy = PrunePolicy(keep_first=2, keep_last=2)
    result = prune(turns, policy)
    _show("pinned_middle_survives", result)
    # Verify the pinned security tool turn is kept.
    pinned_kept = [t for t in result.kept if t.pinned]
    assert len(pinned_kept) == 1
    assert "SECURITY SCAN" in pinned_kept[0].content
    assert result.marker_inserted


def scenario_token_ceiling_drops_more() -> None:
    # Build a conversation that survives turn-band pruning but blows the token budget,
    # forcing additional drops from the kept band (oldest first).
    turns = [Turn("system", "You are a long-context test fixture.")]
    # 6 conversation turns of varying size.
    sizes = [50, 200, 30, 400, 25, 60]
    for i, sz in enumerate(sizes):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append(Turn(role, ("word " * sz).strip(), tokens=sz))
    # keep_first=2 keep_last=3 means with 6 convo turns, only 1 middle gets dropped
    # by band logic. Then a 200-token ceiling has to drop more.
    policy = PrunePolicy(
        keep_first=2,
        keep_last=3,
        max_total_tokens=200,
        token_count_fn=lambda t: t.tokens if t.tokens is not None else len(t.content.split()),
    )
    result = prune(turns, policy)
    _show("token_ceiling_drops_more", result)
    assert result.kept_token_count <= 200 or any(
        "budget breached" in d for d in result.decisions
    )


def main() -> None:
    scenario_short_no_prune_needed()
    print()
    scenario_long_middle_drop()
    print()
    scenario_pinned_middle_survives()
    print()
    scenario_token_ceiling_drops_more()
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()

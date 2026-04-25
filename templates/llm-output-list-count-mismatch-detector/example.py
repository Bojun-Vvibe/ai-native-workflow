"""Worked example: 6 prompt/output pairs covering every verdict + a no-promise control."""

from __future__ import annotations

from detector import detect, extract_bullets, extract_promised_count

CASES = [
    # 1. clean — promised 5, delivered 5, all terminate cleanly.
    (
        "Give me 5 reasons to switch to a write-ahead log.",
        """1. Crash safety: the log is durable before the page cache is.
2. Faster commits because sequential writes beat random writes.
3. Replication: streaming the log gives you a free standby.
4. Point-in-time recovery from a base backup plus log replay.
5. Easier debugging: every state change is a line in a file.""",
    ),
    # 2. under — promised 5, delivered 3 (the model ran out of ideas).
    (
        "List five ways to reduce embedding cost.",
        """- Cache identical inputs.
- Coalesce small requests into batches.
- Drop near-duplicate documents before indexing.""",
    ),
    # 3. over — promised 3, delivered 5 (the model padded).
    (
        "Name three failure modes of retry-with-backoff.",
        """1. Thundering herd when many clients retry on the same window boundary.
2. Goodput collapse when the upstream is the bottleneck and retries amplify load.
3. Idempotency violations when args drift across attempts.
4. Wasted work when the operation has already succeeded but the response was lost.
5. Budget exhaustion eating real user-facing capacity.""",
    ),
    # 4. truncated_tail — promised 5, delivered 5, but the last bullet looks chopped
    # mid-sentence (no terminal punctuation, much shorter than peers, ends in "and").
    (
        "Give me 5 reasons HTTP/2 helps long-tail latency.",
        """- Header compression collapses repeated header bytes across many requests.
- Stream multiplexing lets one connection carry many concurrent requests.
- Server push can prime the client cache before the client asks.
- Binary framing is cheaper to parse than HTTP/1.1 ASCII.
- Request prioritization lets clients hint and""",
    ),
    # 5. no_list — promised 4 but the model wrote prose with no bullets.
    (
        "List 4 advantages of column-oriented storage.",
        "Column-oriented storage compresses each column independently which works well "
        "because column values share a domain; it also lets the engine read only the "
        "columns a query actually projects, which dominates query latency for wide tables. "
        "Vectorized execution is a natural fit. Updates are harder.",
    ),
    # 6. no_promise — control: prompt has no count word at all.
    (
        "Explain what a circuit breaker is.",
        """- It cuts off calls to a failing dependency so the failure does not cascade.
- It probes periodically to detect recovery.""",
    ),
    # 7. ordinal_gap — promised 4, delivered 4, but ordinals jump 1, 2, 4, 5.
    (
        "Give me 4 steps to onboard a new agent profile.",
        """1. Write the profile YAML.
2. Add the agent to the dispatcher allowlist.
4. Smoke-test against a small mission.
5. Promote to the standard rotation.""",
    ),
]


def main() -> None:
    for i, (prompt, output) in enumerate(CASES, start=1):
        promised = extract_promised_count(prompt)
        bullets = extract_bullets(output)
        report = detect(prompt, output)
        print(f"--- case {i} ---")
        print(f"prompt: {prompt}")
        print(f"promised={promised}  delivered={len(bullets)}  verdict={report.verdict}")
        for f in report.findings:
            print(f"  finding: {f}")
        print()

    # Runtime invariants — every case must produce its designed verdict.
    expected_verdicts = ["clean", "under", "over", "truncated_tail", "no_list_promised_was_made", "no_promise", "ordinal_gap"]
    actual = [detect(p, o).verdict for (p, o) in CASES]
    assert actual == expected_verdicts, f"verdict drift: {actual}"
    print("# All runtime invariants pass.")


if __name__ == "__main__":
    main()

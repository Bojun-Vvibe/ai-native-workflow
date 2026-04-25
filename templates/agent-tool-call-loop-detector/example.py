"""Worked example: feed several synthetic tool-call histories through the
loop detector and print the verdict for each scenario."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from template import ToolCall, detect_loop  # noqa: E402


SCENARIOS: list[tuple[str, list[ToolCall]]] = [
    (
        "healthy_progress",
        [
            ToolCall("read_file", {"path": "a.py"}),
            ToolCall("grep", {"pattern": "foo"}),
            ToolCall("read_file", {"path": "b.py"}),
            ToolCall("edit", {"path": "b.py", "line": 12}),
            ToolCall("run_tests", {"target": "tests/test_b.py"}),
        ],
    ),
    (
        "exact_repeat_same_grep",
        [
            ToolCall("grep", {"pattern": "TODO"}),
            ToolCall("grep", {"pattern": "TODO"}),
            ToolCall("grep", {"pattern": "TODO"}),
            ToolCall("grep", {"pattern": "TODO"}),
        ],
    ),
    (
        "abab_cycle_read_then_edit_same_file",
        [
            ToolCall("read_file", {"path": "x.py"}),
            ToolCall("edit", {"path": "x.py", "line": 1}),
            ToolCall("read_file", {"path": "x.py"}),
            ToolCall("edit", {"path": "x.py", "line": 1}),
            ToolCall("read_file", {"path": "x.py"}),
            ToolCall("edit", {"path": "x.py", "line": 1}),
        ],
    ),
    (
        "no_progress_single_call_only",
        [
            ToolCall("list_dir", {"path": "."}),
            ToolCall("list_dir", {"path": "."}),
            ToolCall("list_dir", {"path": "."}),
        ],
    ),
    (
        "args_canonicalized_repeats_caught",
        [
            ToolCall("http_get", {"url": "https://example.test/", "headers": {"a": 1, "b": 2}}),
            ToolCall("http_get", {"url": "https://example.test/", "headers": {"b": 2, "a": 1}}),
            ToolCall("http_get", {"url": "https://example.test/", "headers": {"a": 1, "b": 2}}),
        ],
    ),
]


def main() -> int:
    print("agent-tool-call-loop-detector :: worked example")
    print("=" * 60)
    looped_count = 0
    for name, history in SCENARIOS:
        report = detect_loop(history, window=8, repeat_threshold=3, cycle_min_len=4)
        status = "LOOP" if report.looped else "ok"
        if report.looped:
            looped_count += 1
        print(f"[{status:>4}] {name:42s} reason={report.reason}")
        if report.looped:
            for k, v in report.detail.items():
                print(f"         . {k}: {v}")
    print("=" * 60)
    print(f"scenarios={len(SCENARIOS)} looped_detected={looped_count} healthy={len(SCENARIOS) - looped_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

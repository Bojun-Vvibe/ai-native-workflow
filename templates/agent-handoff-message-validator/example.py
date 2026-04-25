"""Worked example: validate four handoff messages, one good and three
flavors of broken, and print the per-message verdict."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from template import validate_handoff  # noqa: E402


GOOD = {
    "from_agent": "scout",
    "to_agent": "actor",
    "task_id": "WP-2026-0042",
    "summary": (
        "Repo uses pytest with fixtures in conftest.py. The failing test "
        "tests/test_parser.py::test_unicode_escape touches the lexer at "
        "src/lexer.py:212. See artifact:lexer-snippet for the relevant "
        "lines and artifact:trace-2026 for the failing run trace."
    ),
    "next_action": "implement",
    "artifacts": [
        {"kind": "code_snippet", "ref": "lexer-snippet"},
        {"kind": "trace", "ref": "trace-2026"},
    ],
    "open_questions": [
        "Should surrogate-pair handling match Python 3.12 behavior or stay strict?"
    ],
}

MISSING_FIELDS = {
    "from_agent": "planner",
    "to_agent": "implementer",
    "task_id": "WP-9",  # too short, also will fail regex
    "summary": "do the thing",
    # missing next_action, artifacts, open_questions
}

BAD_REFS_AND_ENUMS = {
    "from_agent": "reviewer",
    "to_agent": "reviewer",  # same as from_agent
    "task_id": "WP-2026-0099",
    "summary": "Looks fine, see artifact:does-not-exist for the diff.",
    "next_action": "merge_now",  # not in enum
    "artifacts": [
        {"kind": "diff", "ref": "diff-aaa"},
        {"kind": "", "ref": "diff-aaa"},  # empty kind, duplicate ref
    ],
    "open_questions": ["", "valid q?"],
}

BANNED_TOKEN_LEAK = {
    "from_agent": "scout",
    "to_agent": "actor",
    "task_id": "WP-2026-0500",
    "summary": "Investigate the SUPER-SECRET-CODENAME pipeline (see artifact:notes for context).",
    "next_action": "investigate",
    "artifacts": [{"kind": "note", "ref": "notes"}],
    "open_questions": ["Anything else?"],
}


SCENARIOS = [
    ("good_handoff", GOOD, None),
    ("missing_fields_and_short_task_id", MISSING_FIELDS, None),
    ("bad_refs_same_agent_bad_enum", BAD_REFS_AND_ENUMS, None),
    ("banned_token_leak", BANNED_TOKEN_LEAK, ["super-secret-codename"]),
]


def main() -> int:
    print("agent-handoff-message-validator :: worked example")
    print("=" * 64)
    pass_count = 0
    for name, msg, banned in SCENARIOS:
        result = validate_handoff(msg, banned_tokens=banned)
        verdict = "PASS" if result.ok else "FAIL"
        if result.ok:
            pass_count += 1
        print(f"[{verdict}] {name}")
        for e in result.errors:
            print(f"  ERROR  : {e}")
        for w in result.warnings:
            print(f"  warn   : {w}")
        if not result.errors and not result.warnings:
            print("  (clean)")
        print()
    print("=" * 64)
    print(f"scenarios={len(SCENARIOS)} pass={pass_count} fail={len(SCENARIOS) - pass_count}")
    # Also show the JSON shape of one result so callers know what to expect.
    sample = validate_handoff(GOOD)
    print("sample_result_shape =", json.dumps(sample.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

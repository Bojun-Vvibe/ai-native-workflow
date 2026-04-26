"""
Worked example for llm-output-json-trailing-comma-and-comment-detector.

Run:
    python3 example.py

Output is pasted verbatim into README.md.
"""

import json

from validator import (
    detect_jsonc_artifacts,
    format_report,
    strip_artifacts,
)


CASES = [
    (
        "01 strict-clean JSON",
        '{"id": 42, "tags": ["a", "b"]}',
    ),
    (
        "02 trailing comma in object",
        '{"id": 42, "name": "foo",}',
    ),
    (
        "03 trailing comma in array",
        '{"items": [1, 2, 3,]}',
    ),
    (
        "04 // line comment",
        '{\n  // human-friendly note\n  "ok": true\n}',
    ),
    (
        "05 /* block comment */ between fields",
        '{"a": 1, /* removed for v2 */ "b": 2}',
    ),
    (
        "06 the kitchen sink",
        '{\n  // header\n  "cfg": {\n    "retries": 3,  /* was 5 */\n    "tags": ["x", "y",],\n  },\n}',
    ),
    (
        "07 comma-comment lookalike inside a string is NOT a finding",
        '{"sql": "SELECT a, /* not a real comment */ b FROM t WHERE x = 3,"}',
    ),
    (
        "08 unterminated block comment",
        '{"a": 1 /* oops where does this end',
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== case {name} ===")
        findings = detect_jsonc_artifacts(text)
        print(format_report(findings))
        if findings and not any(
            f.kind == "unterminated_block_comment" for f in findings
        ):
            cleaned, _ = strip_artifacts(text)
            print(f"--- after strip_artifacts ---")
            print(cleaned)
            try:
                obj = json.loads(cleaned)
                print(f"json.loads OK -> keys={sorted(obj.keys()) if isinstance(obj, dict) else type(obj).__name__}")
            except json.JSONDecodeError as e:
                print(f"json.loads FAILED: {e}")
        print()


if __name__ == "__main__":
    main()

"""End-to-end smoke test for model-output-truncation-detector.

Feeds five representative outputs through the detector and prints
the verdict + signals. Builds a continuation prompt for the worst
case to show the second half of the API.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector import build_continuation_prompt, detect  # noqa: E402


CASES = [
    (
        "clean_with_stop",
        "Here is the answer: 42. The reasoning is straightforward.",
        "stop",
    ),
    (
        "length_signal_only",
        "Step one is to initialize the buffer. Step two is to populate it with",
        "length",
    ),
    (
        "unclosed_code_fence_no_signal",
        "Here is the function:\n\n```python\ndef foo():\n    return 1\n",
        None,
    ),
    (
        "mid_bullet_no_signal",
        "The plan:\n- Read the input\n- Validate the schema\n- Apply the",
        None,
    ),
    (
        "stop_with_innocent_code_block",
        "Final code:\n\n```python\nprint('done')\n```\n",
        "stop",
    ),
    (
        "ends_mid_word_no_signal",
        "The recommended approach is to first check the connectivity of the upstr",
        None,
    ),
]


def main() -> None:
    print(f"{'case':35} {'verdict':18} signals")
    print("-" * 90)
    worst: tuple[str, str, str] | None = None
    for name, text, fr in CASES:
        v = detect(text, finish_reason=fr)
        sig_str = ",".join(v.signals) or "-"
        print(f"{name:35} {v.verdict:18} {sig_str}")
        if v.verdict == "TRUNCATED" and worst is None:
            worst = (name, text, fr or "")

    # Sanity-check expected verdicts
    assert detect(CASES[0][1], "stop").verdict == "CLEAN"
    assert detect(CASES[1][1], "length").verdict == "TRUNCATED"
    assert detect(CASES[2][1], None).verdict in ("LIKELY_TRUNCATED", "TRUNCATED")
    assert detect(CASES[3][1], None).verdict in ("LIKELY_TRUNCATED", "SUSPICIOUS")
    assert detect(CASES[4][1], "stop").verdict == "CLEAN"
    assert detect(CASES[5][1], None).verdict in ("SUSPICIOUS", "LIKELY_TRUNCATED")

    print()
    print("=== continuation prompt for first TRUNCATED case ===")
    name, text, fr = worst  # type: ignore[misc]
    v = detect(text, finish_reason=fr)
    prompt = build_continuation_prompt(
        v,
        original_request="Walk me through how to load and validate config.",
        partial=text,
    )
    print(prompt)

    print()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

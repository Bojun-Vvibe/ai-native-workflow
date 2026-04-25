"""Worked example for ``llm-output-language-mismatch-detector``.

Five scenarios, one summary line each, all deterministic.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detector import detect, LanguageConfigError


def run() -> None:
    cases = [
        # (label, text, expected, min_ratio)
        (
            "1. clean english reply",
            "The build passed all 47 tests. No regressions detected on main.",
            "latin",
            0.7,
        ),
        (
            "2. silent drift to chinese",
            "构建已经成功。所有四十七个测试都通过了，主分支没有回归。",
            "latin",
            0.7,
        ),
        (
            "3. code-switched mid-answer (heavy mix)",
            "Build OK. 所有测试都通过了，主分支没有任何回归，可以合并。Done.",
            "latin",
            0.7,
        ),
        (
            "4. pure-symbol output (no language signal)",
            '{"x":1,"y":2,"z":[3,4,5,6,7,8,9,10,11,12]}',
            "latin",
            0.7,
        ),
        (
            "5. expected cjk, got cjk",
            "构建已经成功。所有四十七个测试都通过了，主分支没有回归，可以安全合并。",
            "cjk",
            0.7,
        ),
    ]

    for label, text, expected, min_ratio in cases:
        r = detect(text, expected, min_ratio=min_ratio)
        print(
            f"{label}\n"
            f"   verdict={r.verdict} expected={r.expected} dominant={r.dominant} "
            f"ratio={r.expected_ratio:.2f} classified={r.classified_chars}\n"
            f"   reason: {r.reason}\n"
        )

    # Demonstrate config-time error.
    print("6. unknown family raises LanguageConfigError:")
    try:
        detect("hello", "klingon")
    except LanguageConfigError as e:
        print(f"   raised: {e}\n")

    # Runtime invariants.
    r1 = detect("The build passed.", "latin", min_chars=5)
    assert r1.verdict == "match" and r1.expected_ratio == 1.0, r1
    r2 = detect("构建成功。", "latin", min_chars=3)
    assert r2.verdict == "mismatch" and r2.dominant == "cjk", r2
    print("invariants ok: pure-latin match=1.0, pure-cjk mismatch->cjk dominant")


if __name__ == "__main__":
    run()

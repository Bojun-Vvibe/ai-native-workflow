#!/usr/bin/env python3
"""Worked example for the vaultwarden-signups-allowed detector.

Loads every ``examples/bad_*.txt`` and ``examples/good_*.txt`` file,
runs ``detector.scan`` on each blob, and prints a short report.

Run with stdlib python3:
    python3 run_example.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from detector import scan  # noqa: E402


def main() -> int:
    examples = HERE / "examples"
    bad_files = sorted(examples.glob("bad_*.txt"))
    good_files = sorted(examples.glob("good_*.txt"))

    bad_hits = 0
    good_hits = 0

    print("== bad samples (should each produce >=1 finding) ==")
    for f in bad_files:
        findings = scan(f.read_text(encoding="utf-8"))
        status = "FLAG" if findings else "miss"
        if findings:
            bad_hits += 1
        print(f"  {f.name}: {status} ({len(findings)} finding(s))")
        for line, reason in findings:
            print(f"    L{line}: {reason}")

    print()
    print("== good samples (should each produce 0 findings) ==")
    for f in good_files:
        findings = scan(f.read_text(encoding="utf-8"))
        status = "ok" if not findings else "FALSE-POSITIVE"
        if findings:
            good_hits += 1
        print(f"  {f.name}: {status} ({len(findings)} finding(s))")
        for line, reason in findings:
            print(f"    L{line}: {reason}")

    print()
    print(f"summary: bad={bad_hits}/{len(bad_files)} good_false_positives={good_hits}/{len(good_files)}")
    if bad_hits == len(bad_files) and good_hits == 0:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

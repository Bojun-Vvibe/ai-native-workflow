#!/usr/bin/env python3
"""Runnable harness for the prometheus-no-web-tls detector."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from detector import detect  # noqa: E402


def main() -> int:
    bad_dir = HERE / "examples" / "bad"
    good_dir = HERE / "examples" / "good"

    bad_files = sorted(p for p in bad_dir.iterdir() if p.is_file())
    good_files = sorted(p for p in good_dir.iterdir() if p.is_file())

    bad_hits = 0
    for p in bad_files:
        if detect(p.read_text(encoding="utf-8")):
            bad_hits += 1
        else:
            print(f"FAIL: bad sample not flagged: {p.name}")

    good_fps = 0
    for p in good_files:
        if detect(p.read_text(encoding="utf-8")):
            good_fps += 1
            print(f"FAIL: good sample falsely flagged: {p.name}")

    if bad_hits == len(bad_files) and good_fps == 0:
        print(f"PASS bad={bad_hits}/{len(bad_files)} good={good_fps}/{len(good_files)}")
        return 0
    print(f"FAIL bad={bad_hits}/{len(bad_files)} good_fp={good_fps}/{len(good_files)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

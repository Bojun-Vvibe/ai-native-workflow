"""CLI: fingerprint a prompt package or diff two of them."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import diff as diff_mod
from .fingerprint import fingerprint


def _load(p: str) -> dict:
    return json.loads(Path(p).read_text())


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: cli fingerprint <pkg.json>", file=sys.stderr)
        print("       cli diff <a-pkg.json> <b-pkg.json>", file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "fingerprint" and len(argv) == 3:
        print(json.dumps(fingerprint(_load(argv[2])), indent=2))
        return 0
    if cmd == "diff" and len(argv) == 4:
        a = fingerprint(_load(argv[2]))
        b = fingerprint(_load(argv[3]))
        report = diff_mod.diff(a, b)
        print(diff_mod.render_markdown(report))
        return 0 if not report["drift"] else 1
    print("bad arguments", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

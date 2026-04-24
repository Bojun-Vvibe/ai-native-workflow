#!/usr/bin/env python3
"""Convenience wrapper: `approve.py CASE` == `snapshot.py approve CASE`.

Mostly here so docs can say `python3 bin/approve.py 002` for parity
with the workflow described in README.md. Forwards everything to
snapshot.py.
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    snapshot_py = os.path.join(here, "snapshot.py")
    # Forward as: snapshot.py approve <case_id> [other args...]
    forwarded = [snapshot_py, "approve"] + argv[1:]
    os.execv(sys.executable, [sys.executable] + forwarded)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

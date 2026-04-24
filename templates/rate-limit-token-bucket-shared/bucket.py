#!/usr/bin/env python3
"""Shared token-bucket rate limiter.

Coordinates rate across multiple processes on a single host using a
file-locked JSON state file. Stdlib only.

CLI:
    python bucket.py init   <state_file> <capacity> <refill_per_sec>
    python bucket.py acquire <state_file> <n> [--now-ns N]
    python bucket.py peek   <state_file> [--now-ns N]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from typing import Tuple


def _read_state(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_state_atomic(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, sort_keys=True)
    os.replace(tmp, path)


def init_bucket(path: str, capacity: int, refill_per_sec: float, now_ns: int) -> dict:
    state = {
        "capacity": int(capacity),
        "refill_per_sec": float(refill_per_sec),
        "tokens": float(capacity),
        "last_refill_ns": int(now_ns),
    }
    _write_state_atomic(path, state)
    return state


def _refill(state: dict, now_ns: int) -> dict:
    elapsed_s = max(0.0, (now_ns - state["last_refill_ns"]) / 1e9)
    new_tokens = min(
        float(state["capacity"]),
        float(state["tokens"]) + elapsed_s * float(state["refill_per_sec"]),
    )
    state["tokens"] = new_tokens
    state["last_refill_ns"] = int(now_ns)
    return state


def acquire(path: str, n: float, now_ns: int) -> Tuple[bool, float, dict]:
    """Try to acquire n tokens. Returns (ok, wait_s_if_not_ok, state)."""
    # Open with O_RDWR; create lockfile if missing.
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(fd, "r+", encoding="utf-8", closefd=False) as f:
            f.seek(0)
            state = json.load(f)
        state = _refill(state, now_ns)
        if state["tokens"] >= n:
            state["tokens"] = float(state["tokens"]) - float(n)
            _write_state_atomic(path, state)
            return True, 0.0, state
        wait_s = (float(n) - float(state["tokens"])) / float(state["refill_per_sec"])
        _write_state_atomic(path, state)
        return False, wait_s, state
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def peek(path: str, now_ns: int) -> dict:
    state = _read_state(path)
    return _refill(dict(state), now_ns)


def _now_ns_or(arg: int | None) -> int:
    return int(arg) if arg is not None else time.monotonic_ns()


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("state_file")
    pi.add_argument("capacity", type=int)
    pi.add_argument("refill_per_sec", type=float)
    pi.add_argument("--now-ns", type=int, default=None)

    pa = sub.add_parser("acquire")
    pa.add_argument("state_file")
    pa.add_argument("n", type=float)
    pa.add_argument("--now-ns", type=int, default=None)

    pp = sub.add_parser("peek")
    pp.add_argument("state_file")
    pp.add_argument("--now-ns", type=int, default=None)

    args = p.parse_args(argv)
    now_ns = _now_ns_or(args.now_ns)

    if args.cmd == "init":
        st = init_bucket(args.state_file, args.capacity, args.refill_per_sec, now_ns)
        print(json.dumps({"initialized": True, "tokens": st["tokens"]}, sort_keys=True))
        return 0
    if args.cmd == "acquire":
        ok, wait_s, st = acquire(args.state_file, args.n, now_ns)
        print(json.dumps(
            {"ok": ok, "wait_s": round(wait_s, 6), "tokens_left": round(st["tokens"], 6)},
            sort_keys=True,
        ))
        return 0 if ok else 2
    if args.cmd == "peek":
        st = peek(args.state_file, now_ns)
        print(json.dumps({"tokens": round(st["tokens"], 6)}, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

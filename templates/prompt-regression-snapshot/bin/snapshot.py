#!/usr/bin/env python3
"""Prompt-regression snapshot runner. Stdlib only.

Subcommands:
    run     - run all fixtures, diff outputs vs snapshots, print report.
    diff    - print the diff for one case.
    approve - promote a CHANGED case's new output to the snapshot.
    rebless - update prompt_sha in snapshots without changing output.

Fixture file (one per case) at <fixtures-dir>/<case-id>.json:
    {
      "case_id": "001-extract-user",
      "input": "Alice (id 42) email alice@example.com",
      "format": "json",                 // "json" or "prose"
      "mock_outputs": {
        "v1": "...",                    // keyed by prompt_sha
        "v2": "..."
      }
    }

Snapshot file (one per case) at <snapshots-dir>/<case-id>.json:
    {
      "case_id": "001-extract-user",
      "fixture_sha": "...",
      "prompt_sha": "v1",
      "model": "mock-1",
      "temperature": 0,
      "captured_at": "2026-04-24T10:00:00Z",
      "output_canonical": "...",
      "output_raw": "..."
    }

Exit codes:
    0  - all MATCH (and no orphan snapshots)
    1  - one or more CHANGED, NEW (with --strict-new), or MISSING
    2  - usage error
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import sys
from typing import Any


# ---------- Mock model -----------------------------------------

class MockModel:
    """Returns mock_outputs[prompt_sha] from the fixture.

    Replace with your SDK call. The contract: pure function of
    (input, prompt_sha). Determinism is the whole point.
    """

    name = "mock-1"
    temperature = 0

    def complete(self, fixture: dict[str, Any], prompt_sha: str) -> str:
        outs = fixture.get("mock_outputs", {})
        if prompt_sha not in outs:
            raise KeyError(f"fixture {fixture['case_id']!r} has no "
                           f"mock_output for prompt_sha={prompt_sha!r}")
        return outs[prompt_sha]


# ---------- Canonicalisation ------------------------------------

def canonicalise(raw: str, fmt: str) -> str:
    if fmt == "json":
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to prose canonicalisation if not valid JSON;
            # the diff will still be meaningful.
            return canonicalise(raw, "prose")
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)
    if fmt == "prose":
        lines = [ln.rstrip() for ln in raw.splitlines()]
        # Drop trailing blank lines.
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)
    raise ValueError(f"unknown format: {fmt}")


def sha_short(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# ---------- IO helpers -----------------------------------------

def load_json(path: str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def save_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def list_cases(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(directory)
        if name.endswith(".json")
    )


# ---------- Verdicts -------------------------------------------

VERDICT_MATCH = "MATCH"
VERDICT_CHANGED = "CHANGED"
VERDICT_NEW = "NEW"
VERDICT_MISSING = "MISSING"


def evaluate_case(case_id: str, fixtures_dir: str, snapshots_dir: str,
                  prompt_sha: str, model: MockModel) -> dict[str, Any]:
    fix_path = os.path.join(fixtures_dir, f"{case_id}.json")
    snap_path = os.path.join(snapshots_dir, f"{case_id}.json")

    fixture_present = os.path.exists(fix_path)
    snapshot_present = os.path.exists(snap_path)

    if not fixture_present and snapshot_present:
        return {"case_id": case_id, "verdict": VERDICT_MISSING,
                "snap_path": snap_path}

    fixture = load_json(fix_path)
    fmt = fixture.get("format", "json")
    raw = model.complete(fixture, prompt_sha)
    canonical = canonicalise(raw, fmt)
    fixture_sha = sha_short(json.dumps(fixture, sort_keys=True))

    new_snapshot = {
        "case_id": case_id,
        "fixture_sha": fixture_sha,
        "prompt_sha": prompt_sha,
        "model": model.name,
        "temperature": model.temperature,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"),
        "output_canonical": canonical,
        "output_raw": raw,
    }

    if not snapshot_present:
        return {"case_id": case_id, "verdict": VERDICT_NEW,
                "snap_path": snap_path, "new": new_snapshot}

    old = load_json(snap_path)
    if old.get("output_canonical") == canonical:
        verdict = VERDICT_MATCH
    else:
        verdict = VERDICT_CHANGED
    return {"case_id": case_id, "verdict": verdict,
            "snap_path": snap_path, "old": old, "new": new_snapshot}


# ---------- Subcommands ----------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    fixtures = list_cases(args.fixtures)
    snapshots = list_cases(args.snapshots)
    all_cases = sorted(set(fixtures) | set(snapshots))
    model = MockModel()

    results = [evaluate_case(c, args.fixtures, args.snapshots,
                             args.prompt_sha, model) for c in all_cases]

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    print(f"Snapshot run @ prompt_sha={args.prompt_sha} model={model.name}")
    print(f"Cases: {len(results)}  ", end="")
    print("  ".join(f"{k}={counts.get(k, 0)}" for k in
                    [VERDICT_MATCH, VERDICT_CHANGED,
                     VERDICT_NEW, VERDICT_MISSING]))
    print()

    bad = 0
    for r in results:
        v = r["verdict"]
        marker = {"MATCH": "  ", "CHANGED": "! ",
                  "NEW": "+ ", "MISSING": "? "}[v]
        print(f"{marker}{v:<8} {r['case_id']}")
        if v == VERDICT_CHANGED:
            old_lines = r["old"]["output_canonical"].splitlines()
            new_lines = r["new"]["output_canonical"].splitlines()
            for line in difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"{r['case_id']}.snapshot",
                tofile=f"{r['case_id']}.new", lineterm="",
            ):
                print(f"        {line}")
        if v == VERDICT_CHANGED:
            bad += 1
        if v == VERDICT_MISSING:
            bad += 1
        if v == VERDICT_NEW and args.strict_new:
            bad += 1

    if args.write_new:
        for r in results:
            if r["verdict"] == VERDICT_NEW:
                save_json(r["snap_path"], r["new"])
                print(f"  wrote new snapshot: {r['snap_path']}")

    return 1 if (args.strict and bad) else (1 if bad else 0)


def cmd_diff(args: argparse.Namespace) -> int:
    model = MockModel()
    r = evaluate_case(args.case_id, args.fixtures, args.snapshots,
                      args.prompt_sha, model)
    if r["verdict"] != VERDICT_CHANGED:
        print(f"{r['case_id']}: {r['verdict']} (no diff)")
        return 0
    old_lines = r["old"]["output_canonical"].splitlines()
    new_lines = r["new"]["output_canonical"].splitlines()
    for line in difflib.unified_diff(old_lines, new_lines,
                                     fromfile="snapshot",
                                     tofile="new", lineterm=""):
        print(line)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    model = MockModel()
    r = evaluate_case(args.case_id, args.fixtures, args.snapshots,
                      args.prompt_sha, model)
    if r["verdict"] not in (VERDICT_CHANGED, VERDICT_NEW):
        print(f"{r['case_id']}: {r['verdict']}; nothing to approve",
              file=sys.stderr)
        return 1
    save_json(r["snap_path"], r["new"])
    print(f"approved {r['case_id']}: snapshot updated at {r['snap_path']}")
    return 0


def cmd_rebless(args: argparse.Namespace) -> int:
    """Bump prompt_sha in MATCH snapshots without changing output."""
    model = MockModel()
    cases = list_cases(args.snapshots)
    bumped = 0
    for c in cases:
        r = evaluate_case(c, args.fixtures, args.snapshots,
                          args.prompt_sha, model)
        if r["verdict"] == VERDICT_MATCH:
            old = r["old"]
            if old.get("prompt_sha") != args.prompt_sha:
                old["prompt_sha"] = args.prompt_sha
                old["captured_at"] = r["new"]["captured_at"]
                save_json(r["snap_path"], old)
                bumped += 1
                print(f"reblessed {c} -> prompt_sha={args.prompt_sha}")
    print(f"reblessed {bumped} snapshot(s)")
    return 0


# ---------- argparse -------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="snapshot.py")
    p.add_argument("--fixtures", default="fixtures",
                   help="directory of fixture JSON files (default: fixtures)")
    p.add_argument("--snapshots", default="snapshots",
                   help="directory of snapshot JSON files (default: snapshots)")
    p.add_argument("--prompt-sha", default="v1",
                   help="caller-supplied prompt identity (default: v1)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_run = sub.add_parser("run", help="diff all fixtures vs snapshots")
    sp_run.add_argument("--strict", action="store_true",
                        help="exit non-zero on any CHANGED")
    sp_run.add_argument("--strict-new", action="store_true",
                        help="treat NEW as failure too")
    sp_run.add_argument("--write-new", action="store_true",
                        help="auto-write snapshots for NEW cases (bootstrap)")
    sp_run.set_defaults(func=cmd_run)

    sp_diff = sub.add_parser("diff", help="show diff for one case")
    sp_diff.add_argument("case_id")
    sp_diff.set_defaults(func=cmd_diff)

    sp_app = sub.add_parser("approve", help="promote new output to snapshot")
    sp_app.add_argument("case_id")
    sp_app.set_defaults(func=cmd_approve)

    sp_reb = sub.add_parser("rebless",
                            help="bump prompt_sha on MATCH cases (no output change)")
    sp_reb.set_defaults(func=cmd_rebless)
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv[1:])
    # Default --strict on for `run` so CI is the default behaviour.
    if args.cmd == "run" and not hasattr(args, "strict"):
        args.strict = True
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

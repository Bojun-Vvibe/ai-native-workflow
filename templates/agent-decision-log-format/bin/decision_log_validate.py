#!/usr/bin/env python3
"""Validator for the agent-decision-log-format JSONL spec.

Usage:
  decision_log_validate.py LOG.jsonl

Exits 0 on success (all records valid), 1 on validation errors,
2 on bad input. Emits a JSON report on stdout.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

REQUIRED_FIELDS = {
    "ts": str,
    "mission_id": str,
    "step_id": str,
    "step_index": int,
    "prompt_hash": str,
    "model": str,
    "tools_called": list,
    "exit_state": str,
}

ALLOWED_EXIT_STATES = {"continue", "done", "handoff", "giveup", "error"}
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# Conservative ISO-8601 UTC: YYYY-MM-DDTHH:MM:SS(.fff)?Z
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _err(line: int, mission_id: str, code: str, detail: str) -> dict:
    return {"line": line, "mission_id": mission_id, "code": code, "detail": detail}


def validate_record(rec: Any, line: int) -> list[dict]:
    errors: list[dict] = []
    mid = rec.get("mission_id", "<unknown>") if isinstance(rec, dict) else "<unknown>"

    if not isinstance(rec, dict):
        return [_err(line, mid, "bad_type", "record is not a JSON object")]

    for field, ftype in REQUIRED_FIELDS.items():
        if field not in rec:
            errors.append(_err(line, mid, "missing_field", f"missing {field!r}"))
            continue
        # bool is a subclass of int in Python; reject bool when int is expected.
        if ftype is int and isinstance(rec[field], bool):
            errors.append(
                _err(line, mid, "bad_type", f"{field} must be int, got bool")
            )
            continue
        if not isinstance(rec[field], ftype):
            errors.append(
                _err(
                    line,
                    mid,
                    "bad_type",
                    f"{field} must be {ftype.__name__}, got {type(rec[field]).__name__}",
                )
            )

    # If any required field is missing/badly typed we still try the rest.
    if "exit_state" in rec and isinstance(rec["exit_state"], str):
        if rec["exit_state"] not in ALLOWED_EXIT_STATES:
            errors.append(
                _err(
                    line,
                    mid,
                    "bad_enum",
                    f"exit_state {rec['exit_state']!r} not in {sorted(ALLOWED_EXIT_STATES)}",
                )
            )
    if "prompt_hash" in rec and isinstance(rec["prompt_hash"], str):
        if not HASH_RE.match(rec["prompt_hash"]):
            errors.append(
                _err(line, mid, "bad_hash_format", "prompt_hash does not match sha256:<64hex>")
            )
    if "ts" in rec and isinstance(rec["ts"], str):
        if not ISO_RE.match(rec["ts"]):
            errors.append(_err(line, mid, "bad_iso8601", f"ts {rec['ts']!r} is not ISO-8601 UTC"))
    if "step_index" in rec and isinstance(rec["step_index"], int) and not isinstance(rec["step_index"], bool):
        if rec["step_index"] < 0:
            errors.append(_err(line, mid, "bad_type", "step_index must be >= 0"))

    if isinstance(rec.get("tools_called"), list):
        for i, t in enumerate(rec["tools_called"]):
            if not isinstance(t, dict):
                errors.append(_err(line, mid, "bad_type", f"tools_called[{i}] not an object"))
                continue
            if not isinstance(t.get("name"), str):
                errors.append(_err(line, mid, "missing_field", f"tools_called[{i}].name"))
            if not isinstance(t.get("ok"), bool):
                errors.append(_err(line, mid, "bad_type", f"tools_called[{i}].ok must be bool"))
            d = t.get("duration_ms")
            if not isinstance(d, int) or isinstance(d, bool):
                errors.append(_err(line, mid, "bad_type", f"tools_called[{i}].duration_ms must be int"))
            elif d < 0:
                errors.append(_err(line, mid, "negative_duration", f"tools_called[{i}].duration_ms={d}"))

    return errors


def validate_log(path: str) -> dict:
    errors: list[dict] = []
    total = 0
    valid = 0
    seen_missions: set[str] = set()
    completed_missions: set[str] = set()
    expected_step: dict[str, int] = {}

    try:
        f = open(path)
    except OSError as e:
        return {"input": path, "fatal": str(e), "exit": 2}

    with f:
        for lineno, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            total += 1
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                errors.append(_err(lineno, "<unknown>", "parse_error", str(e)))
                continue

            rec_errs = validate_record(rec, lineno)

            mid = rec.get("mission_id") if isinstance(rec, dict) else None
            if isinstance(mid, str):
                seen_missions.add(mid)

                if mid in completed_missions:
                    rec_errs.append(
                        _err(lineno, mid, "record_after_done", "mission already terminated by done")
                    )

                idx = rec.get("step_index")
                if isinstance(idx, int) and not isinstance(idx, bool):
                    want = expected_step.get(mid, 0)
                    if idx != want:
                        rec_errs.append(
                            _err(
                                lineno,
                                mid,
                                "non_monotonic_step_index",
                                f"expected step_index={want}, got {idx}",
                            )
                        )
                    # Always advance the counter to avoid cascading errors.
                    expected_step[mid] = max(want, idx) + 1

                if rec.get("exit_state") == "done":
                    completed_missions.add(mid)

            if rec_errs:
                errors.extend(rec_errs)
            else:
                valid += 1

    return {
        "input": path,
        "total_records": total,
        "valid_records": valid,
        "invalid_records": total - valid,
        "missions_seen": len(seen_missions),
        "missions_completed": len(completed_missions),
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: decision_log_validate.py LOG.jsonl", file=sys.stderr)
        return 2
    report = validate_log(argv[1])
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("exit") == 2:
        return 2
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

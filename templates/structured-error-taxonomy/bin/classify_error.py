#!/usr/bin/env python3
"""structured-error-taxonomy — classifier + validator.

Classifies a raw error record into a canonical (class, retryability,
attribution) tuple drawn from a small, stable enum so that downstream
runtime-control templates (model-fallback-ladder, tool-call-retry-envelope,
tool-call-circuit-breaker, agent-cost-budget-envelope) can branch on the
*class* instead of fragile substring matching against vendor messages.

Inputs (one JSON object per line, on stdin or via --in):

    {
      "id": "call-1",                    # required, opaque str
      "source": "model" | "tool" | "host", # required
      "vendor_code": "rate_limit_exceeded", # optional, vendor-native
      "http_status": 429,                # optional int
      "message": "Rate limit reached"    # optional free text
    }

Output (JSON object per line):

    {
      "id": "call-1",
      "class": "rate_limited",            # one of CLASSES
      "retryability": "retry_after",      # one of RETRYABILITY
      "attribution": "vendor",            # one of ATTRIBUTION
      "matched_rule": "rule_id_or_default"
    }

Exit codes:
    0 — every input matched a non-default rule
    1 — at least one input fell through to the catch-all `unknown` class
    2 — input was malformed (missing required field, bad JSON)

The classifier is a *pure function*: rules are evaluated top-to-bottom,
first match wins, and a deterministic catch-all guarantees a verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Stable enums — additions are backwards-compatible, removals are not.
CLASSES = (
    "rate_limited",
    "content_filter",
    "auth",
    "quota_exhausted",
    "context_length",
    "tool_timeout",
    "tool_unavailable",
    "tool_bad_input",
    "host_io",
    "transient_network",
    "unknown",
)

RETRYABILITY = (
    "retry_now",       # immediate retry safe (idempotent transient)
    "retry_after",     # retry after a delay (rate limit, 503)
    "retry_with_edit", # only retry if request is changed (context_length, bad_input)
    "do_not_retry",    # terminal (auth, content_filter)
)

ATTRIBUTION = (
    "vendor",   # provider's fault (rate limit, 5xx)
    "caller",   # our request was bad (auth, bad_input, context_length)
    "tool",     # downstream tool (timeout, unavailable)
    "host",     # local infra (host_io)
    "unknown",
)

# Rules are (rule_id, predicate, (class, retryability, attribution)).
# First match wins. Predicates are pure functions of the input record.
def _has_status(rec: dict, *codes: int) -> bool:
    return rec.get("http_status") in codes


def _vendor_in(rec: dict, *needles: str) -> bool:
    code = (rec.get("vendor_code") or "").lower()
    return any(n in code for n in needles)


def _msg_in(rec: dict, *needles: str) -> bool:
    msg = (rec.get("message") or "").lower()
    return any(n in msg for n in needles)


RULES = [
    ("rl_429",          lambda r: _has_status(r, 429),
     ("rate_limited", "retry_after", "vendor")),
    ("rl_vendor",       lambda r: _vendor_in(r, "rate_limit", "ratelimit", "too_many_requests"),
     ("rate_limited", "retry_after", "vendor")),
    ("auth_401_403",    lambda r: _has_status(r, 401, 403),
     ("auth", "do_not_retry", "caller")),
    ("auth_vendor",     lambda r: _vendor_in(r, "invalid_api_key", "unauthorized", "permission_denied"),
     ("auth", "do_not_retry", "caller")),
    ("content_filter",  lambda r: _vendor_in(r, "content_filter", "content_policy", "safety"),
     ("content_filter", "do_not_retry", "caller")),
    ("quota",           lambda r: _vendor_in(r, "quota", "billing", "insufficient_quota"),
     ("quota_exhausted", "do_not_retry", "caller")),
    ("context_length",  lambda r: _vendor_in(r, "context_length", "max_tokens", "too_long")
                                 or _msg_in(r, "context length", "maximum context"),
     ("context_length", "retry_with_edit", "caller")),
    ("tool_timeout",    lambda r: r.get("source") == "tool"
                                 and (_msg_in(r, "timed out", "timeout", "deadline")
                                      or _has_status(r, 408, 504)),
     ("tool_timeout", "retry_after", "tool")),
    ("tool_unavail",    lambda r: r.get("source") == "tool" and _has_status(r, 502, 503),
     ("tool_unavailable", "retry_after", "tool")),
    ("tool_bad_input",  lambda r: r.get("source") == "tool" and _has_status(r, 400, 422),
     ("tool_bad_input", "retry_with_edit", "caller")),
    ("host_io",         lambda r: r.get("source") == "host" and _msg_in(r, "ioerror", "no space", "permission denied", "broken pipe"),
     ("host_io", "do_not_retry", "host")),
    ("net_5xx",         lambda r: _has_status(r, 500, 502, 503, 504),
     ("transient_network", "retry_after", "vendor")),
    ("net_msg",         lambda r: _msg_in(r, "connection reset", "connection refused", "econnreset", "etimedout"),
     ("transient_network", "retry_now", "vendor")),
]

DEFAULT = ("unknown", "do_not_retry", "unknown")
DEFAULT_RULE_ID = "default"


def classify(rec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rec, dict):
        raise ValueError("record must be an object")
    if "id" not in rec or not isinstance(rec["id"], str):
        raise ValueError("missing or non-string 'id'")
    if "source" not in rec or rec["source"] not in ("model", "tool", "host"):
        raise ValueError("missing or invalid 'source' (must be model|tool|host)")
    for rule_id, pred, verdict in RULES:
        try:
            ok = pred(rec)
        except Exception:
            ok = False
        if ok:
            cls, retry, attr = verdict
            return {
                "id": rec["id"],
                "class": cls,
                "retryability": retry,
                "attribution": attr,
                "matched_rule": rule_id,
            }
    cls, retry, attr = DEFAULT
    return {
        "id": rec["id"],
        "class": cls,
        "retryability": retry,
        "attribution": attr,
        "matched_rule": DEFAULT_RULE_ID,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--in", dest="infile", default="-",
                   help="input JSONL path (default: stdin)")
    args = p.parse_args(argv)

    src = sys.stdin if args.infile == "-" else open(args.infile, "r", encoding="utf-8")
    saw_default = False
    line_no = 0
    try:
        for raw in src:
            line_no += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as e:
                sys.stderr.write(f"line {line_no}: bad JSON: {e}\n")
                return 2
            try:
                out = classify(rec)
            except ValueError as e:
                sys.stderr.write(f"line {line_no}: {e}\n")
                return 2
            print(json.dumps(out, sort_keys=True))
            if out["matched_rule"] == DEFAULT_RULE_ID:
                saw_default = True
    finally:
        if src is not sys.stdin:
            src.close()
    return 1 if saw_default else 0


if __name__ == "__main__":
    sys.exit(main())

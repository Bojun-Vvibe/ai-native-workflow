#!/usr/bin/env python3
"""
classify-retry.py — given a tool-call failure, decide retry-class.

Stdlib only. Reads a failure descriptor on stdin (JSON), prints
one of: retry_safe | retry_unsafe | retry_with_backoff | do_not_retry
followed by a human-readable reason.

The classifier lives in the agent loop, NOT in the host. Only the
agent loop knows whether the model has 'given up' on this tool call
and moved on to a different one.

Failure descriptor schema:
{
  "kind":          "transport" | "http_status" | "envelope_response"
                   | "exception" | "model_decision",
  "http_status":   <int, optional>,
  "exception":     "<class-name>", optional,
  "dedup_status":  "<value from response envelope>", optional,
  "retry_after_ms": <int, optional>,
  "model_moved_on": <bool, optional>
}
"""

from __future__ import annotations
import argparse
import json
import sys
from typing import Any, Dict, Tuple

# --- decision tables -------------------------------------------------

# HTTP statuses that almost always mean "transport blip; retry safe".
_TRANSIENT_HTTP = {502, 503, 504, 521, 522, 523, 524}

# HTTP statuses that mean "back off and try again".
_BACKOFF_HTTP = {429}

# HTTP statuses that mean "the host actively rejected; do NOT retry".
_HARD_HTTP = {400, 401, 403, 404, 405, 410, 422}

# Exceptions that are transport-level by name. Wide net on purpose.
_TRANSIENT_EXC = {
    "ConnectionResetError",
    "ConnectionAbortedError",
    "ConnectionRefusedError",
    "TimeoutError",
    "asyncio.TimeoutError",
    "RemoteProtocolError",       # httpx
    "ProtocolError",             # urllib3
    "IncompleteRead",
    "BrokenPipeError",
    "EOFError",                  # SSE/WebSocket truncated
    "ServerDisconnectedError",   # aiohttp
}

# dedup_status values that map to non-retryable.
_HARD_DEDUP = {"rejected_max_attempts", "rejected_key_collision"}


def classify(failure: Dict[str, Any]) -> Tuple[str, str]:
    kind = failure.get("kind")

    if kind == "model_decision" and failure.get("model_moved_on"):
        return ("do_not_retry",
                "agent loop already gave up; let dedup table handle it")

    if kind == "envelope_response":
        ds = failure.get("dedup_status")
        if ds in _HARD_DEDUP:
            return ("retry_unsafe",
                    f"host returned {ds}; this will not improve on retry")
        if ds == "expired":
            return ("retry_with_backoff",
                    "deadline passed; retry only after extending deadline")
        # executed_now / replayed_from_cache should not reach the classifier.

    if kind == "http_status":
        status = failure.get("http_status")
        if status in _BACKOFF_HTTP:
            ra = failure.get("retry_after_ms", 1000)
            return ("retry_with_backoff",
                    f"HTTP {status}; back off {ra}ms then retry")
        if status in _TRANSIENT_HTTP:
            return ("retry_safe",
                    f"HTTP {status}; transient gateway/server error")
        if status in _HARD_HTTP:
            return ("retry_unsafe",
                    f"HTTP {status}; host actively rejected the call")
        # 5xx not in the transient set is treated cautiously.
        if status and 500 <= status < 600:
            return ("retry_with_backoff",
                    f"HTTP {status}; unknown 5xx, prefer back-off")
        return ("retry_unsafe", f"HTTP {status}; unrecognised non-2xx")

    if kind == "exception":
        exc = failure.get("exception", "")
        if exc in _TRANSIENT_EXC or any(t in exc for t in _TRANSIENT_EXC):
            return ("retry_safe", f"{exc}: transport-layer failure")
        return ("retry_unsafe", f"{exc}: not a known transport exception")

    if kind == "transport":
        return ("retry_safe", "explicit transport failure")

    return ("retry_unsafe", "unknown failure kind; refusing to retry")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", nargs="?", default="-")
    args = p.parse_args()
    data = sys.stdin.read() if args.file == "-" else open(args.file).read()
    decision, reason = classify(json.loads(data))
    print(json.dumps({"decision": decision, "reason": reason},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

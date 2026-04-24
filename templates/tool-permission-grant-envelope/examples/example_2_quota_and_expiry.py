#!/usr/bin/env python3
"""Example 2: quota exhaustion and expiry, replayed from a JSONL event log.

Shows the canonical replay pattern: rebuild `usage` from disk, then
each new decision is a pure function of (grants, usage, request).
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grant_engine import CallRequest, Grant, decide, replay_log  # noqa: E402

GRANTS = [
    Grant(
        grant_id="g-net-search",
        agent_id="mission-9",
        tool="net.search",
        scopes=("network",),
        max_calls=3,
        expires_at=1700000300,  # ~5 minutes after t=1700000000
    ),
]

# Simulate an existing event log with two prior allowed calls.
events = [
    {"grant_id": "g-net-search", "ts": 1700000010},
    {"grant_id": "g-net-search", "ts": 1700000050},
]
log_path = os.path.join(tempfile.mkdtemp(prefix="grant-log-"), "events.jsonl")
with open(log_path, "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")

usage = replay_log(GRANTS, log_path)
print(f"replayed usage: {usage}")
print()

REQUESTS = [
    # 5. Allowed: third (and final) call.
    CallRequest("mission-9", "net.search", ("network",),
                {"q": "site:example.com"}, now=1700000100),
    # 6. Denied: quota exhausted (3/3 used).
    CallRequest("mission-9", "net.search", ("network",),
                {"q": "again"}, now=1700000110),
    # 7. Denied: expired grant (now > expires_at), even before quota check.
    CallRequest("mission-9", "net.search", ("network",),
                {"q": "later"}, now=1700000400),
]

for i, req in enumerate(REQUESTS, 5):
    d = decide(GRANTS, usage, req)
    if d.allowed:
        usage[d.grant_id] = usage.get(d.grant_id, 0) + 1
        # In a real host, also append to the log here.
        with open(log_path, "a") as f:
            f.write(json.dumps({"grant_id": d.grant_id, "ts": req.now}) + "\n")
    print(f"req {i}: now={req.now}")
    print(f"  -> {json.dumps(d.to_dict(), sort_keys=True)}")
    print()

print(f"final usage: {usage}")

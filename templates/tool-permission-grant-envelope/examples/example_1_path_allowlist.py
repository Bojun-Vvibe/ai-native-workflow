#!/usr/bin/env python3
"""Example 1: write-fs grant with arg_allow restricting to a single dir.

Demonstrates that the engine surfaces the *specific* deny reason
(argument_not_allowed) rather than rolling up to a generic "denied".
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grant_engine import CallRequest, Grant, decide  # noqa: E402

GRANTS = [
    Grant(
        grant_id="g-fs-tmp-write",
        agent_id="mission-42",
        tool="fs.write",
        scopes=("write",),
        max_calls=10,
        expires_at=2000000000,
        arg_allow={"dir": ["/tmp/mission-42", "/tmp/mission-42/out"]},
    ),
]
USAGE: dict[str, int] = {}

REQUESTS = [
    # 1. Allowed: dir is in allowlist, scope ok, quota fresh.
    CallRequest("mission-42", "fs.write", ("write",),
                {"dir": "/tmp/mission-42", "name": "a.txt"}, now=1700000000),
    # 2. Denied: dir not in allowlist (must be specific, not generic).
    CallRequest("mission-42", "fs.write", ("write",),
                {"dir": "/etc", "name": "passwd"}, now=1700000000),
    # 3. Denied: tool not granted at all.
    CallRequest("mission-42", "fs.delete", ("write",),
                {"dir": "/tmp/mission-42"}, now=1700000000),
    # 4. Denied: scope escalation attempt (asking for admin on a write-only grant).
    CallRequest("mission-42", "fs.write", ("write", "admin"),
                {"dir": "/tmp/mission-42", "name": "ok.txt"}, now=1700000000),
]

for i, req in enumerate(REQUESTS, 1):
    d = decide(GRANTS, USAGE, req)
    if d.allowed:
        USAGE[d.grant_id] = USAGE.get(d.grant_id, 0) + 1
    print(f"req {i}: tool={req.tool} args={json.dumps(req.args, sort_keys=True)}")
    print(f"  -> {json.dumps(d.to_dict(), sort_keys=True)}")
    print()

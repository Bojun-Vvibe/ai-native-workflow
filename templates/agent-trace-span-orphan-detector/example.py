"""
Worked example: agent-trace-span-orphan-detector

Five synthetic traces covering every detection class plus a clean baseline.
Run:
    python3 example.py
"""

from __future__ import annotations

import json

from detector import detect


def banner(title: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)


# ----------------------------------------------------------------------------
# 1. Healthy trace — single root, every parent resolves, all spans closed.
# ----------------------------------------------------------------------------
healthy = [
    {"span_id": "root", "parent_span_id": None,   "trace_id": "T1",
     "name": "mission",  "started_at": 100.0, "finished_at": 200.0},
    {"span_id": "plan",  "parent_span_id": "root", "trace_id": "T1",
     "name": "plan",     "started_at": 101.0, "finished_at": 110.0},
    {"span_id": "tool1", "parent_span_id": "plan", "trace_id": "T1",
     "name": "read_file", "started_at": 111.0, "finished_at": 112.0},
    {"span_id": "tool2", "parent_span_id": "plan", "trace_id": "T1",
     "name": "edit_file", "started_at": 113.0, "finished_at": 120.0},
]

# ----------------------------------------------------------------------------
# 2. Orphan — tool's parent_span_id refers to a span_id that's not in the trace.
#    Common cause: span batch was split across two flush windows and one
#    flush dropped on the floor.
# ----------------------------------------------------------------------------
orphan = [
    {"span_id": "root", "parent_span_id": None,        "trace_id": "T2",
     "name": "mission",  "started_at": 100.0, "finished_at": 200.0},
    {"span_id": "tool1", "parent_span_id": "missing-span", "trace_id": "T2",
     "name": "read_file", "started_at": 111.0, "finished_at": 112.0},
]

# ----------------------------------------------------------------------------
# 3. Multiple roots — two spans claim parent=None inside one trace_id.
#    Common cause: client process forked and both halves emitted a "root".
# ----------------------------------------------------------------------------
multi_root = [
    {"span_id": "rootA", "parent_span_id": None, "trace_id": "T3",
     "name": "mission-A", "started_at": 100.0, "finished_at": 200.0},
    {"span_id": "rootB", "parent_span_id": None, "trace_id": "T3",
     "name": "mission-B", "started_at": 101.0, "finished_at": 201.0},
    {"span_id": "tool",  "parent_span_id": "rootA", "trace_id": "T3",
     "name": "read",     "started_at": 102.0, "finished_at": 103.0},
]

# ----------------------------------------------------------------------------
# 4. Cycle — tool1's parent is tool2 and tool2's parent is tool1.
#    Common cause: bug in async parent-context propagation library.
# ----------------------------------------------------------------------------
cycle = [
    {"span_id": "root",  "parent_span_id": None,    "trace_id": "T4",
     "name": "mission",  "started_at": 100.0, "finished_at": 200.0},
    {"span_id": "tool1", "parent_span_id": "tool2", "trace_id": "T4",
     "name": "read",     "started_at": 110.0, "finished_at": 111.0},
    {"span_id": "tool2", "parent_span_id": "tool1", "trace_id": "T4",
     "name": "edit",     "started_at": 112.0, "finished_at": 113.0},
]

# ----------------------------------------------------------------------------
# 5. Cross-trace + dangling_open — tool's parent lives in a different trace
#    AND a tool span never got a finished_at.
# ----------------------------------------------------------------------------
mixed = [
    {"span_id": "root",  "parent_span_id": None,   "trace_id": "T5",
     "name": "mission",  "started_at": 100.0, "finished_at": 200.0},
    {"span_id": "alien", "parent_span_id": None,   "trace_id": "T-OTHER",
     "name": "elsewhere", "started_at":  50.0, "finished_at":  60.0},
    {"span_id": "tool1", "parent_span_id": "alien", "trace_id": "T5",
     "name": "read",     "started_at": 110.0, "finished_at": 111.0},
    {"span_id": "tool2", "parent_span_id": "root",  "trace_id": "T5",
     "name": "long_op",  "started_at": 120.0, "finished_at": None},
    {"span_id": "tool3", "parent_span_id": "root",  "trace_id": "T5",
     "name": "latest",   "started_at": 199.0, "finished_at": 199.5},
]

cases = [
    ("01 healthy",       healthy),
    ("02 orphan",        orphan),
    ("03 multiple_roots", multi_root),
    ("04 cycle",         cycle),
    ("05 cross+dangling", mixed),
]

for label, trace in cases:
    banner(label)
    report = detect(trace)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    print()

# Summary tally
banner("summary")
totals: dict[str, int] = {}
for label, trace in cases:
    rep = detect(trace)
    for f in rep.findings:
        totals[f.kind] = totals.get(f.kind, 0) + 1
print(json.dumps({"finding_kind_totals": dict(sorted(totals.items()))}, indent=2))

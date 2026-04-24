"""Worked example 1 — root → 2 nested tool calls under one trace.

Demonstrates:
  - One trace_id flows through three calls (root + two children).
  - Each child carries the parent's span as parent_span_id.
  - Wire header round-trips: serialize on the client, parse on the tool side,
    open a child span, serialize again for the next hop.
  - validate_records returns ok=True; tree walk is depth-aware.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trace import Recorder, child, new_root, parse, render_tree, validate_records


def main() -> None:
    rng = random.Random(20260425)  # deterministic for stable example output
    rec = Recorder()

    # ------------------------------------------------------------------
    # Orchestrator opens the root span.
    # ------------------------------------------------------------------
    root_ctx = new_root(rng)
    s_root = rec.open(root_ctx, "mission.run", started_ms=0)
    print("root header on the wire:")
    print(" ", root_ctx.header())

    # ------------------------------------------------------------------
    # Orchestrator calls tool A. It serializes the child header, sends it
    # over the wire, the tool parses it and opens its own span.
    # ------------------------------------------------------------------
    a_ctx_client = child(root_ctx, rng)
    wire_a = a_ctx_client.header()
    a_ctx_server = parse(wire_a)
    assert a_ctx_server == a_ctx_client, "header round-trip must be lossless"
    s_a = rec.open(a_ctx_server, "tool.fetch_user", started_ms=10)
    s_a.finish("ok", ended_ms=42, http_status=200, bytes_in=512)

    # ------------------------------------------------------------------
    # Tool A in turn calls tool B (nested). Parent is now A, not root.
    # ------------------------------------------------------------------
    b_ctx_client = child(a_ctx_server, rng)
    wire_b = b_ctx_client.header()
    b_ctx_server = parse(wire_b)
    s_b = rec.open(b_ctx_server, "tool.cache_lookup", started_ms=15)
    s_b.finish("ok", ended_ms=18, cache="hit", key_prefix="u:42")

    s_root.finish("ok", ended_ms=50)

    print("\nrecorded spans (raw):")
    for r in rec.records():
        print(" ", json.dumps(r, sort_keys=True))

    print("\nvalidation report:")
    report = validate_records(rec.records())
    print(" ", json.dumps(report, sort_keys=True))
    assert report["ok"], "valid trace must validate"

    print("\ntree view:")
    print(render_tree(rec.tree(root_ctx.trace_id)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Worked example: a 'fetch many pages' tool under the laddered timeout.

Scenario: an agent has a tool that walks a paginated API and returns
parsed records. Pages are slow (~80ms each) and the agent's per-call
budget is small. We want:

  - If we finish all pages inside soft, return the full result.
  - If soft fires partway through, stop at a page boundary and return
    the pages we already have, marked partial.
  - If the tool is misbehaving (stuck in a single page), hard cancel
    and surface whatever we last published.
  - If even hard doesn't unblock it (e.g. C extension), kill protects
    the orchestrator.
"""

from __future__ import annotations

import json
import time

from ladder import LadderConfig, run_with_ladder


def make_paginated_tool(total_pages: int, ms_per_page: int, *, stuck_on: int = -1):
    """Return a tool that fetches `total_pages` pages.

    If `stuck_on >= 0`, the tool will sleep forever on that page (simulating
    an unresponsive backend / C-ext blocking call).
    """
    def tool(should_soft_exit, publish):
        pages = []
        for i in range(total_pages):
            if should_soft_exit():
                # Cooperative early exit at a page boundary.
                publish({"pages": pages, "stopped_after_page": i - 1})
                return {"pages": pages, "complete": False}
            if i == stuck_on:
                # Simulate a backend that hangs hard.
                time.sleep(60.0)
            time.sleep(ms_per_page / 1000.0)
            pages.append({"page": i, "rows": [i * 10, i * 10 + 1]})
            publish({"pages": pages})
        return {"pages": pages, "complete": True}
    return tool


def _summarize(label: str, r) -> None:
    d = r.to_dict()
    # For readability in the printed output: count pages, drop the bulky list.
    if isinstance(d.get("value"), dict) and "pages" in d["value"]:
        d["value"] = {"page_count": len(d["value"]["pages"]),
                      "complete": d["value"].get("complete")}
    if isinstance(d.get("partial"), dict) and "pages" in d["partial"]:
        d["partial"] = {"page_count": len(d["partial"]["pages"])}
    print(f"\n--- {label} ---")
    print(json.dumps(d, indent=2))


def main() -> None:
    print("=== worked example: paginated fetch under laddered timeout ===")
    cfg = LadderConfig(soft_s=0.30, hard_s=0.50, kill_s=0.70)
    print(f"config: soft={cfg.soft_s}s hard={cfg.hard_s}s kill={cfg.kill_s}s")

    # Case A: small job, fits inside soft.
    _summarize(
        "A) 3 pages @ 80ms (fits in soft)",
        run_with_ladder(make_paginated_tool(3, 80), cfg),
    )

    # Case B: too many pages; cooperative tool exits at boundary.
    _summarize(
        "B) 12 pages @ 80ms (cooperative soft exit)",
        run_with_ladder(make_paginated_tool(12, 80), cfg),
    )

    # Case C: backend hangs forever on page 2; hard cancel.
    _summarize(
        "C) page-2 backend hang (hard timeout, partial = pages 0..1)",
        run_with_ladder(make_paginated_tool(12, 80, stuck_on=2), cfg),
    )


if __name__ == "__main__":
    main()

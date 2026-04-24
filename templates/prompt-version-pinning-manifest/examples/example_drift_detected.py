"""Example 2: live tuple has drifted (someone bumped temperature
and reworded the system prompt). Drift detector pinpoints the
exact fields and refuses to silently let the change through."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pinmanifest import (  # noqa: E402
    build_manifest,
    detect_drift,
    format_drift_report,
)


PINNED = {
    "system_prompt": "You are a terse summarizer. Output <= 3 bullets.",
    "user_template": "Summarize:\n{document}",
    "model": "claude-opus-4.7",
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 512,
    "tool_signature": None,
}

# someone "tweaked" the deployed agent
LIVE = {
    "system_prompt": "You are a terse summarizer. Output 3 bullets.",  # reworded
    "user_template": "Summarize:\n{document}",
    "model": "claude-opus-4.7",
    "temperature": 0.7,                                                # bumped
    "top_p": 1.0,
    "max_tokens": 512,
    "tool_signature": None,
}


def main() -> None:
    manifest = build_manifest(
        {"summarizer": PINNED}, now_iso="2026-04-24T00:00:00Z"
    )
    report = detect_drift(manifest, "summarizer", LIVE)
    print(format_drift_report(report))
    print()
    if report.drifted:
        print("ACTION: refuse to deploy until pin is updated.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()

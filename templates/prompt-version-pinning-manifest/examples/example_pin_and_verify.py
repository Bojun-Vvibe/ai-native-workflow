"""Example 1: build a manifest, persist it, then re-load and confirm
the live tuple matches the pin (no drift)."""

from __future__ import annotations

import os
import sys
import tempfile

# allow running from the examples/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pinmanifest import (  # noqa: E402
    build_manifest,
    write_manifest,
    load_manifest,
    detect_drift,
    format_drift_report,
)


SUMMARIZER_TUPLE = {
    "system_prompt": "You are a terse summarizer. Output <= 3 bullets.",
    "user_template": "Summarize:\n{document}",
    "model": "claude-opus-4.7",
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 512,
    "tool_signature": None,
}

CLASSIFIER_TUPLE = {
    "system_prompt": "You classify support tickets into {billing, bug, other}.",
    "user_template": "Ticket:\n{ticket}\nLabel:",
    "model": "gpt-4o-mini",
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 8,
    "tool_signature": "label_only_v1",
}


def main() -> None:
    manifest = build_manifest(
        {"summarizer": SUMMARIZER_TUPLE, "classifier": CLASSIFIER_TUPLE},
        now_iso="2026-04-24T00:00:00Z",
    )

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "prompts.lock.json")
        write_manifest(manifest, path)
        reloaded = load_manifest(path)

        print(f"manifest schema_version: {reloaded['schema_version']}")
        print(f"pinned entries        : {sorted(reloaded['entries'])}")
        print(
            "summarizer fp         : "
            + reloaded["entries"]["summarizer"]["fingerprint"][:16]
            + "..."
        )
        print(
            "classifier fp         : "
            + reloaded["entries"]["classifier"]["fingerprint"][:16]
            + "..."
        )

        # live deployment uses identical tuple -> no drift
        report = detect_drift(reloaded, "summarizer", SUMMARIZER_TUPLE)
        print()
        print(format_drift_report(report))


if __name__ == "__main__":
    main()

"""
Worked example for agent-system-prompt-instruction-conflict-detector.

Four synthetic system prompts:
  01 healthy   - clean, no conflicts
  02 polarity  - "always cite urls" + "never include urls"
  03 quantifier- "always show working" + "sometimes show working"
  04 format    - "respond in markdown" + "respond in plain text"
                 plus a list-style conflict in the same prompt
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detector import detect


CASES = [
    (
        "01 healthy",
        """\
You are a careful research assistant.
Always cite the source URL for every factual claim.
Respond in markdown with bullet lists for enumerations.
If you are uncertain, say so explicitly.
""",
    ),
    (
        "02 polarity_conflict",
        """\
You are a research assistant.
Always cite the source URL for every factual claim.
Be concise.
Never cite URLs in your response because they break our renderer.
""",
    ),
    (
        "03 quantifier_conflict",
        """\
You are a math tutor.
Always show your working step by step before giving the final answer.
Sometimes show your working when the student is stuck.
Be encouraging.
""",
    ),
    (
        "04 format_conflict",
        """\
You are a customer-support agent.
Respond in markdown for clarity.
Use bullet lists when enumerating options.
For our voice channel, respond in plain text only.
Use numbered lists so customers can refer to items by number.
""",
    ),
]


def main() -> None:
    grand_tally: dict = {}
    for label, text in CASES:
        print("=" * 72)
        print(label)
        print("=" * 72)
        report = detect(text)
        d = report.to_dict()
        print(json.dumps(d, indent=2, sort_keys=True))
        for k, v in d["finding_kind_totals"].items():
            grand_tally[k] = grand_tally.get(k, 0) + v
        print()

    print("=" * 72)
    print("summary")
    print("=" * 72)
    print(json.dumps(
        {"finding_kind_totals_across_prompts": dict(sorted(grand_tally.items()))},
        indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    main()

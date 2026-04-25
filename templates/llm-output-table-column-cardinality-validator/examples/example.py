"""
Worked example for llm-output-table-column-cardinality-validator.

Five synthetic markdown documents, one per finding class plus a clean
control. Prints one JSON report per document followed by a doc-set
tally.
"""

from __future__ import annotations

import json
import os
import sys

# Allow running as a script directly: `python3 example.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validator import validate


CASES = [
    (
        "01 healthy",
        "Top-of-quarter status report:\n"
        "\n"
        "| service | owner | sev1_last_30d |\n"
        "|---|---|---|\n"
        "| billing | alice | 0 |\n"
        "| search | bob | 2 |\n"
        "| auth | carol | 1 |\n"
        "\n"
        "End of report.\n",
    ),
    (
        "02 missing_delimiter",
        "Quick status:\n"
        "\n"
        "| service | owner | sev1 |\n"
        "| billing | alice | 0 |\n"
        "| search | bob | 2 |\n",
    ),
    (
        "03 column_count_mismatch",
        "Audit log:\n"
        "\n"
        "| ts | actor | action | target |\n"
        "|---|---|---|---|\n"
        "| 2026-04-26T10:00 | alice | promote | billing |\n"
        "| 2026-04-26T10:05 | bob | rotate-secret |\n"
        "| 2026-04-26T10:10 | carol | demote | auth |\n",
    ),
    (
        "04 unescaped_pipe",
        "Pricing tiers:\n"
        "\n"
        "| tier | description | price |\n"
        "|---|---|---|\n"
        "| free | basic features | $0 |\n"
        "| pro | basic | advanced features | $29 |\n"
        "| ent | escaped \\| inside cell is fine | $999 |\n",
    ),
    (
        "05 empty_table + delimiter_count_mismatch",
        "Empty table from a tool that returned no rows:\n"
        "\n"
        "| col_a | col_b | col_c |\n"
        "|---|---|\n"
        "\n"
        "(end of section)\n",
    ),
]


def main() -> None:
    grand_tally: dict = {}
    for label, text in CASES:
        print("=" * 72)
        print(label)
        print("=" * 72)
        report = validate(text)
        d = report.to_dict()
        print(json.dumps(d, indent=2, sort_keys=True))
        for k, v in d["finding_kind_totals"].items():
            grand_tally[k] = grand_tally.get(k, 0) + v
        print()

    print("=" * 72)
    print("summary")
    print("=" * 72)
    print(json.dumps({"finding_kind_totals_across_docs": dict(sorted(grand_tally.items()))}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

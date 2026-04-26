"""Worked example for llm-output-table-column-alignment-consistency-validator.

Embeds a small fixture with three tables exhibiting every finding
class, runs the validator, prints the JSON.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from validator import validate  # noqa: E402


FIXTURE = """\
Q1 results follow.

| Region | Revenue (USD) | Growth (%) |
|--------|---------------|------------|
| AMER   | 1,200         | 8.4        |
| EMEA   | 950           | 3.1        |
| APAC   | 700           | 12.7       |

A second table with a different alignment for column 1:

| Region | Headcount |
|:------:|----------:|
| AMER   | 42        |
| EMEA   | 31        |

And a malformed delimiter on column 2:

| Name | Score |
|------|=======|
| a    | 1     |
| b    | 2     |
"""


def main() -> int:
    findings = validate(FIXTURE)
    print(json.dumps([f.__dict__ for f in findings], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

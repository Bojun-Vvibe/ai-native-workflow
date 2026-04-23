"""
CLI front-end for budget.report().

Usage:
    python -m report --days 7 --by model
    python -m report --days 30 --by model,phase
    python -m report --days 1  --by session_id,tool

Run from inside this directory or PYTHONPATH=src.
"""

import argparse
import sys

from budget import report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7,
                   help="report window in days (default 7)")
    p.add_argument("--by", type=str, default="model",
                   help="comma-separated grouping dims: model,phase,tool,session_id")
    args = p.parse_args()

    by = tuple(d.strip() for d in args.by.split(",") if d.strip())
    print(report(since_days=args.days, by=by))
    return 0


if __name__ == "__main__":
    sys.exit(main())

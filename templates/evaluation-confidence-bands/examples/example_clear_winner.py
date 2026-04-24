"""Example 2: B is meaningfully better (0.92 vs 0.70) on a larger
n=200 eval. The CIs separate cleanly and the harness declares
b_wins."""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from confbands import (  # noqa: E402
    bootstrap_ci,
    compare,
    format_band,
    format_comparison,
)


A_SCORES = [1.0] * 140 + [0.0] * 60       # mean = 0.70, n=200
B_SCORES = [1.0] * 184 + [0.0] * 16       # mean = 0.92, n=200


def main() -> None:
    rng = random.Random(20260424)

    a = bootstrap_ci(A_SCORES, name="baseline", rng=rng,
                     iters=2000, alpha=0.05)
    b = bootstrap_ci(B_SCORES, name="candidate", rng=rng,
                     iters=2000, alpha=0.05)

    print(format_band(a))
    print(format_band(b))
    print()
    cmp = compare(a, b, overlap_margin=0.0)
    print(format_comparison(cmp))


if __name__ == "__main__":
    main()

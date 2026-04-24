"""Example 1: A and B both score around 0.80, ~50 samples each.
The CIs overlap heavily and the harness REFUSES to rank them. This
is the failure mode we actually want — small evals shouldn't crown
winners."""

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


# Two candidates. Both hand-built to average ~0.80 with realistic
# noise. The point: with n=50 the mean difference is not
# distinguishable from sampling noise.
A_SCORES = (
    [1.0] * 40 + [0.0] * 10               # mean = 0.80
)
B_SCORES = (
    [1.0] * 41 + [0.0] * 9                # mean = 0.82
)


def main() -> None:
    rng = random.Random(20260424)         # seeded -> reproducible

    a = bootstrap_ci(A_SCORES, name="prompt_v3", rng=rng,
                     iters=2000, alpha=0.05)
    b = bootstrap_ci(B_SCORES, name="prompt_v4", rng=rng,
                     iters=2000, alpha=0.05)

    print(format_band(a))
    print(format_band(b))
    print()
    cmp = compare(a, b, overlap_margin=0.0)
    print(format_comparison(cmp))


if __name__ == "__main__":
    main()

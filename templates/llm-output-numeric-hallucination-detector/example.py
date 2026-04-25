"""Worked example for llm-output-numeric-hallucination-detector.

Five scenarios demonstrating every verdict:

  1. CLEAN: every output number appears in the source context.
  2. FABRICATED: model invents stats wholesale; no output numbers grounded.
  3. PARTIAL: mix of real-and-fake — the dangerous "looks half-right" case.
  4. UNIT-DRIFT: context says `47 users`, output says `47%` — flagged because
     unit drift IS a fabrication (different claim).
  5. NO_NUMBERS: prose-only answer correctly returns `no_numbers` (distinct
     from clean) so the caller routes to a different validator.

Plus an extraction-only check to show year-vs-int resolution and pinned
number allowlist (`100%`).
"""

from __future__ import annotations

from detector import Number, detect, extract_numbers


def banner(title: str) -> None:
    print()
    print(f"=== {title} ===")


def show_report(report) -> None:
    print(f"  verdict     : {report.verdict}")
    print(f"  output_nums : {[str(n) for n in report.output_numbers]}")
    print(f"  grounded    : {[str(n) for n in report.grounded]}")
    print(f"  ungrounded  : {[str(n) for n in report.ungrounded]}")
    print(f"  ctx_size    : {report.context_size}")
    print(f"  summary     : {report.summary}")


# ---------------------------------------------------------------------------
# Scenario 1: CLEAN
# ---------------------------------------------------------------------------

banner("Scenario 1: CLEAN — every output number grounded")

ctx_1 = (
    "Q3 retention report: 47.3% of users returned within 30 days, "
    "up from 41.2% in Q2. Total active accounts: 12,480. "
    "Average session length 8.5 minutes."
)
out_1 = (
    "Retention rose from 41.2% to 47.3% quarter-over-quarter. "
    "Active accounts now 12,480."
)
print(f"  ctx  : {ctx_1}")
print(f"  out  : {out_1}")
show_report(detect(out_1, ctx_1))


# ---------------------------------------------------------------------------
# Scenario 2: FABRICATED
# ---------------------------------------------------------------------------

banner("Scenario 2: FABRICATED — no output numbers in context")

ctx_2 = "Q3 retention improved over Q2. Engagement is up."
out_2 = (
    "Retention rose from 41.2% to 47.3%. Active accounts grew to 12,480 "
    "and average session length is 8.5 minutes."
)
print(f"  ctx  : {ctx_2}")
print(f"  out  : {out_2}")
show_report(detect(out_2, ctx_2))


# ---------------------------------------------------------------------------
# Scenario 3: PARTIAL — mixed real-and-fake (the dangerous case)
# ---------------------------------------------------------------------------

banner("Scenario 3: PARTIAL — half real, half invented")

ctx_3 = "Active accounts: 12,480. Quarter: Q3."
out_3 = (
    "Active accounts hit 12,480, retention rose to 47.3%, "
    "and average revenue per user is $8.42."
)
print(f"  ctx  : {ctx_3}")
print(f"  out  : {out_3}")
show_report(detect(out_3, ctx_3))


# ---------------------------------------------------------------------------
# Scenario 4: UNIT DRIFT — same digit, different unit = fabrication
# ---------------------------------------------------------------------------

banner("Scenario 4: UNIT DRIFT — context '47 users' != output '47%'")

ctx_4 = "47 users opted in to the beta."
out_4 = "47% of users opted in to the beta."
print(f"  ctx  : {ctx_4}")
print(f"  out  : {out_4}")
show_report(detect(out_4, ctx_4))


# ---------------------------------------------------------------------------
# Scenario 5: NO_NUMBERS — distinct from clean
# ---------------------------------------------------------------------------

banner("Scenario 5: NO_NUMBERS — prose-only answer")

ctx_5 = "Active accounts: 12,480. Retention 47.3%."
out_5 = "Engagement improved this quarter, driven by the new onboarding flow."
print(f"  ctx  : {ctx_5}")
print(f"  out  : {out_5}")
show_report(detect(out_5, ctx_5))


# ---------------------------------------------------------------------------
# Extraction sanity: year vs raw int resolution
# ---------------------------------------------------------------------------

banner("Extraction: year vs raw int (context word resolves ambiguity)")

y1 = extract_numbers("in 2019, sales hit 2019 units")
print("  'in 2019, sales hit 2019 units'")
print(f"    -> {[(str(n), n.unit) for n in y1]}")
print("  Note: first 2019 is year-tagged (preceded by 'in'); second 2019")
print("        is unit='raw' (no year-context word) — dedup keys on (value, unit).")

print()
y2 = extract_numbers("we shipped 2019 widgets")
print("  'we shipped 2019 widgets'")
print(f"    -> {[(str(n), n.unit) for n in y2]}")
print("  Note: no year-context word -> unit='raw'")

# Demonstrate the unit-drift bug class extraction directly:
y3 = extract_numbers("released in 2019; revenue 2019 dollars")
print()
print("  'released in 2019; revenue 2019 dollars'")
print(f"    -> {[(str(n), n.unit) for n in y3]}")
print("  Note: BOTH units present (year + raw) — dedup keys on (value, unit).")


# ---------------------------------------------------------------------------
# Pinned-numbers allowlist (100% always grounded)
# ---------------------------------------------------------------------------

banner("Pinned allowlist: 100% is universally safe")

ctx_6 = "All 12 servers reported in."
out_6 = "100% of the 12 servers reported in."
pinned = frozenset({Number(100.0, "pct")})
print(f"  ctx  : {ctx_6}")
print(f"  out  : {out_6}")
print(f"  pinned: 100%")
show_report(detect(out_6, ctx_6, pinned_numbers=pinned))


# ---------------------------------------------------------------------------
# Final assertions
# ---------------------------------------------------------------------------

assert detect(out_1, ctx_1).verdict == "clean"
assert detect(out_2, ctx_2).verdict == "fabricated"
assert detect(out_3, ctx_3).verdict == "partial"
assert detect(out_4, ctx_4).verdict == "fabricated"
assert detect(out_5, ctx_5).verdict == "no_numbers"
assert detect(out_6, ctx_6, pinned_numbers=pinned).verdict == "clean"

print()
print("=== all 6 verdicts asserted ===")

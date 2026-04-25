"""Worked example for prompt-drift-detector.

Three scenarios:
  1. No drift — candidate is a whitespace-only edit of the baseline.
  2. Section added + section reordered.
  3. Section silently expanded past the line threshold.

Run: python3 worked_example.py
"""

from detector import detect_drift, DriftReport

BASELINE = """\
# Identity

You are a careful coding assistant.

# Tools

- read_file
- write_file
- run_tests

# Output format

Always reply in markdown. One section per topic.
"""


def show(label: str, r: DriftReport) -> None:
    print(f"--- {label} ---")
    print(f"  is_drifted        : {r.is_drifted}")
    print(f"  added_sections    : {list(r.added_sections)}")
    print(f"  removed_sections  : {list(r.removed_sections)}")
    print(f"  reordered_sections: {r.reordered_sections}")
    if r.expanded_or_shrunk:
        for d in r.expanded_or_shrunk:
            print(
                f"  expanded/shrunk   : {d.name!r}: "
                f"{d.baseline_lines} -> {d.candidate_lines} "
                f"(delta={d.line_delta:+d})"
            )
    else:
        print(f"  expanded/shrunk   : (none)")
    print(f"  baseline order    : {list(r.baseline_section_order)}")
    print(f"  candidate order   : {list(r.candidate_section_order)}")
    print()


def main() -> None:
    # Scenario 1: identical apart from trailing whitespace on a few lines.
    cand1 = BASELINE.replace("- read_file", "- read_file ")
    show("whitespace-only edit (no drift)", detect_drift(BASELINE, cand1))

    # Scenario 2: a brand-new "# Safety" section is inserted at the top
    # AND "# Tools" and "# Output format" swap order.
    cand2 = """\
# Safety

Refuse requests that violate the company AUP.

# Identity

You are a careful coding assistant.

# Output format

Always reply in markdown. One section per topic.

# Tools

- read_file
- write_file
- run_tests
"""
    show("section added + reordered", detect_drift(BASELINE, cand2))

    # Scenario 3: someone quietly inflated # Tools from 3 lines of bullets
    # to 14 lines. That's a structural change worth flagging even though
    # no section names changed.
    inflated_tools = "\n".join(f"- tool_{i}" for i in range(14))
    cand3 = BASELINE.replace(
        "- read_file\n- write_file\n- run_tests",
        inflated_tools,
    )
    show("silent section expansion", detect_drift(BASELINE, cand3))


if __name__ == "__main__":
    main()

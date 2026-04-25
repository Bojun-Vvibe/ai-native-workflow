"""
Worked example: assemble a prompt from 6 labeled sections under a tight
30-token budget. Demonstrates priority-ordered keep, truncation of one
section on the boundary, and clean drop of the lowest-priority tail.
"""

from trimmer import PromptBudgetTrimmer, Section, default_count


def main() -> None:
    sections = [
        Section(
            label="system",
            text="You are a careful code reviewer. Be terse. Cite line numbers.",
            priority=100,
        ),
        Section(
            label="task",
            text="Review the diff below and flag correctness issues only.",
            priority=90,
        ),
        Section(
            label="diff",
            text=(
                "diff: changed retry classifier to treat 429 as transient "
                "and 5xx as permanent which inverts prior behavior and "
                "will break the budget integration test that expects "
                "429 to surface as quota_exhausted within two attempts."
            ),
            priority=80,
            truncatable=True,
        ),
        Section(
            label="retrieved_doc_a",
            text="Doc A: project retry policy says 429 is transient.",
            priority=60,
        ),
        Section(
            label="retrieved_doc_b",
            text="Doc B: 5xx historically retried up to three times.",
            priority=55,
        ),
        Section(
            label="scratchpad",
            text="prior turn scratchpad: nothing important here, can drop.",
            priority=10,
        ),
    ]

    budget = 30
    trimmer = PromptBudgetTrimmer(budget=budget, count=default_count)
    result = trimmer.trim(sections)

    print(f"Budget: {budget} tokens")
    print(f"Used:   {result.total_tokens} tokens")
    print(f"Kept:   {result.kept_labels}")
    print(f"Dropped:{result.dropped_labels}")
    print(f"Truncated: {result.truncated_label}")
    print("---- assembled prompt ----")
    print(result.assemble())
    print("---- end ----")

    # Invariants
    assert result.total_tokens <= budget, "trimmer overran the budget"
    assert "system" in result.kept_labels, "highest priority must always be kept"
    assert "scratchpad" in result.dropped_labels, "lowest priority must drop first"
    print("invariants OK")


if __name__ == "__main__":
    main()

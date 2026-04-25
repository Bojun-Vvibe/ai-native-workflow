"""Worked example for prompt-template-variable-validator.

Demonstrates each failure mode the validator catches plus the happy
path. Every failure is a real bug pattern observed in production
prompt-engineering codebases.
"""

from __future__ import annotations

from validator import VarSpec, ValidationError, parse_placeholders, render


TEMPLATE = (
    "You are a code reviewer.\n"
    "Repository: {repo_name}\n"
    "Reviewing PR #{pr_number} by {author}.\n"
    "\n"
    "Diff:\n"
    "{diff}\n"
    "\n"
    "Return JSON only."
)

CONTRACT = {
    "repo_name": VarSpec(type_=str, max_len=200),
    "pr_number": VarSpec(type_=int, max_len=10),
    "author": VarSpec(type_=str, max_len=80),
    "diff": VarSpec(type_=str, max_len=20_000),
}


def expect_error(label: str, fn) -> None:
    try:
        fn()
        print(f"  [{label}] FAIL: did not raise")
    except ValidationError as e:
        print(f"  [{label}] OK ValidationError: {e}")


def main() -> None:
    print("=" * 60)
    print("prompt-template-variable-validator worked example")
    print("=" * 60)

    print("\n[0] parse_placeholders extracts the ordered, deduped set")
    placeholders = parse_placeholders(TEMPLATE)
    print(f"  placeholders = {placeholders}")

    print("\n[1] happy path: contract matches, values match, lengths OK")
    rendered, report = render(
        TEMPLATE,
        values={
            "repo_name": "anomalyco/opencode",
            "pr_number": 1234,
            "author": "alice",
            "diff": "- old line\n+ new line\n",
        },
        contract=CONTRACT,
    )
    print(f"  rendered_length = {report.rendered_length}")
    print(f"  first 80 chars  = {rendered[:80]!r}")

    print("\n[2] caller typo: passes `user_quesiton` for `user_question`")
    typo_template = "Answer: {user_question}"
    typo_contract = {"user_question": VarSpec(type_=str, max_len=500)}
    expect_error(
        "typo",
        lambda: render(typo_template, {"user_quesiton": "hi"}, typo_contract),
    )

    print("\n[3] caller forgot to pass a required variable")
    expect_error(
        "missing",
        lambda: render(
            TEMPLATE,
            values={"repo_name": "x", "pr_number": 1, "author": "a"},
            contract=CONTRACT,
        ),
    )

    print("\n[4] caller passed an extra value not in contract")
    expect_error(
        "extra",
        lambda: render(
            TEMPLATE,
            values={
                "repo_name": "x", "pr_number": 1, "author": "a",
                "diff": "d", "secret_token": "t",
            },
            contract=CONTRACT,
        ),
    )

    print("\n[5] wrong type: pr_number passed as str")
    expect_error(
        "type",
        lambda: render(
            TEMPLATE,
            values={
                "repo_name": "x", "pr_number": "1234", "author": "a", "diff": "d",
            },
            contract=CONTRACT,
        ),
    )

    print("\n[6] None value: would silently render as the literal 'None'")
    null_template = "Question: {q}"
    null_contract = {"q": VarSpec(type_=str, max_len=500)}
    expect_error(
        "none",
        lambda: render(null_template, {"q": None}, null_contract),
    )

    print("\n[7] empty string: caught even though str.format would accept it")
    expect_error(
        "empty",
        lambda: render(null_template, {"q": ""}, null_contract),
    )

    print("\n[8] oversize value: 50 KB diff vs max_len=20_000")
    huge_diff = "x" * 50_000
    expect_error(
        "oversize",
        lambda: render(
            TEMPLATE,
            values={
                "repo_name": "x", "pr_number": 1, "author": "a", "diff": huge_diff,
            },
            contract=CONTRACT,
        ),
    )

    print("\n[9] forbidden constructs in the *template* itself")
    for bad in (
        "Hello {}",                # positional
        "Hello {0}",               # numbered
        "Hello {user.name}",       # attribute access
        "Hello {items[0]}",        # index access
        "Hello {x:>10}",           # format spec
        "Hello {x!r}",             # conversion
    ):
        try:
            parse_placeholders(bad)
            print(f"  [{bad!r}] FAIL: did not raise")
        except ValidationError as e:
            print(f"  [{bad!r}] OK: {e}")

    print("\n" + "=" * 60)
    print("done")


if __name__ == "__main__":
    main()

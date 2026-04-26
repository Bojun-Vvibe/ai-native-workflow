"""Worked-example cases for `llm-output-parenthesis-balance-validator`.

Run: `python3 example.py`
"""

from __future__ import annotations

from validator import validate_parenthesis_balance, format_report


CASES = [
    (
        "01-clean-balanced",
        # Canonical: every `(` has a matching `)`.
        "The model (correctly) closed every parenthesis (even the nested one (here)).\n",
        {},
    ),
    (
        "02-unmatched-open",
        # Classic streaming-LLM bug: opens a paren and forgets to close.
        "We saw three issues (timeout, retry storm, stale cache.\n",
        {},
    ),
    (
        "03-unmatched-close",
        # Over-closed — a stray `)` with no opener.
        "The build failed) and nobody noticed for an hour.\n",
        {},
    ),
    (
        "04-excessive-nesting",
        # Default max_depth=3 is exceeded; only ONE finding for the run.
        "Logs (level=info (subsystem=auth (tenant=acme (region=us-east))) ) here.\n",
        {},
    ),
    (
        "05-permissive-nesting",
        # Same input, max_depth=4 — now passes the depth check.
        "Logs (level=info (subsystem=auth (tenant=acme (region=us-east))) ) here.\n",
        {"max_depth": 4},
    ),
    (
        "06-parens-inside-fenced-code-skipped",
        # Parens inside a fenced block must NOT count toward balance.
        "Prose with one (paren) outside.\n"
        "```python\n"
        "print(\"hello (world)\")\n"
        "if (x): pass\n"
        "```\n"
        "More prose, also balanced (here).\n",
        {},
    ),
    (
        "07-parens-inside-inline-code-skipped",
        # Inline `code(span)` parens are skipped; prose parens still count.
        "Use `print(x)` to log, but the prose paren (this one) is real.\n"
        "And here is `another(unmatched` span that the validator ignores.\n",
        {},
    ),
    (
        "08-strict-no-nesting",
        # max_depth=1 forbids any nested paren.
        "Outer (with inner (nested) text) here.\n",
        {"max_depth": 1},
    ),
    (
        "09-multiple-unmatched-on-one-line",
        # Two unmatched opens AND one unmatched close on the same line.
        "Bad ((line)) is fine, but ( and ( and )))) here.\n",
        {},
    ),
    (
        "10-empty-input",
        "",
        {},
    ),
]


def render_input(text: str) -> str:
    if text == "":
        return "  | <empty>"
    parts = []
    for line in text.split("\n"):
        vis = line.replace("\t", "\\t")
        parts.append(f"  | {vis}\\n")
    if parts and parts[-1] == "  | \\n":
        parts[-1] = "  | "
    return "\n".join(parts)


def main() -> None:
    for name, text, kwargs in CASES:
        print(f"=== {name} ===")
        print("input:")
        print(render_input(text))
        if kwargs:
            print(f"params: {kwargs}")
        findings = validate_parenthesis_balance(text, **kwargs)
        print(format_report(findings))


if __name__ == "__main__":
    main()

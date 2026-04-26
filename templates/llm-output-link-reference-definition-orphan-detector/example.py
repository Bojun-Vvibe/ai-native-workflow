"""Worked example: 7 cases proving the link-reference detector.

Run: ``python3 example.py``
"""

from __future__ import annotations

from validator import detect, format_report


CASES = [
    (
        "01 clean — every reference resolves, every definition is used",
        """\
See the [project README][readme] and the [API docs][api].

[readme]: https://example.org/readme.html
[api]: https://example.org/api.html
""",
    ),
    (
        "02 undefined reference (truncated definitions block)",
        """\
The deploy follows the [runbook][runbook] under failure.

(definitions block was lost mid-generation)
""",
    ),
    (
        "03 orphan definition (edit removed the prose, left the def)",
        """\
The previous paragraph used to mention the postmortem template here.
Now it does not.

[postmortem]: https://example.org/postmortem
""",
    ),
    (
        "04 duplicate definitions with conflicting URLs",
        """\
Read the [spec][spec] before merging.

[spec]: https://example.org/spec-v1.html
[spec]: https://example.org/spec-v2.html
""",
    ),
    (
        "05 empty label — collapsed reference with empty body",
        """\
For details see [][].
""",
    ),
    (
        "06 case mismatch — reference resolves but the casing drifted",
        """\
Auth flow uses [OAuth][OAuth] with PKCE.

[oauth]: https://example.org/oauth
""",
    ),
    (
        "07 fence-aware: a [fake_ref] inside a code block must NOT flag",
        """\
The reference parser ignores brackets in code blocks:

```python
def parse(line):
    return line.startswith("[fake_ref]")
```

But this real one is undefined: [missing_ref][missing_ref].
""",
    ),
]


def main() -> None:
    for name, text in CASES:
        print(f"=== case {name} ===")
        findings = detect(text)
        print(format_report(findings), end="")
        print()


if __name__ == "__main__":
    main()

"""Worked example: six cases for the bare-URL vs markdown-link detector."""

from detector import detect_url_styles, evaluate_consistency, format_report


def run(label: str, text: str, **kw) -> None:
    print(f"=== {label} ===")
    findings = detect_url_styles(text)
    verdict = evaluate_consistency(findings, **kw)
    print(format_report(findings, verdict))
    print()


def main() -> None:
    # 01 clean: only inline markdown links, no code
    run("01 all inline markdown links",
        "See [the spec](https://example.com/spec) and "
        "[the rfc](https://example.com/rfc) for details.")

    # 02 clean: only bare URLs (consistent, just bare-style)
    run("02 all bare urls",
        "Refs: https://example.com/a, https://example.com/b, "
        "and https://example.com/c.")

    # 03 mixed: inline link + bare URL + autolink — three styles in one doc
    run("03 mixed three styles in prose",
        "Background: [overview](https://example.com/overview). "
        "Mirror: https://example.org/mirror. "
        "Source: <https://example.net/src>.")

    # 04 code-aware: bare URL inside a fenced code block must NOT pull
    # the document toward "mixed_styles". Prose stays consistent.
    run("04 prose with bare url only inside fenced code (default policy)",
        "Read [the docs](https://example.com/docs) first.\n\n"
        "```\n"
        "curl -s https://example.com/raw | sh\n"
        "```\n\n"
        "Then [follow up](https://example.com/next).")

    # 05 same input as 04 but strict policy (include_code=True): code URL
    # now counts and the verdict flips to mixed_styles. Demonstrates the
    # operator knob.
    run("05 same as 04 but include_code=True (strict)",
        "Read [the docs](https://example.com/docs) first.\n\n"
        "```\n"
        "curl -s https://example.com/raw | sh\n"
        "```\n\n"
        "Then [follow up](https://example.com/next).",
        include_code=True)

    # 06 reference-style markdown links: legitimate fourth form. Default
    # policy buckets them with inline markdown_link, so a doc using
    # [text][label] consistently is "consistent".
    run("06 reference-style markdown links collapse with inline by default",
        "See [the spec][s] and [the rfc][r].\n\n"
        "[s]: https://example.com/spec\n"
        "[r]: https://example.com/rfc\n")


if __name__ == "__main__":
    main()

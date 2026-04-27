"""Worked example for the link-reference-definition duplicate-label detector.

Each case is a small markdown snippet. Running this module prints
findings for every case so a human can eyeball the detector's behavior
and so CI can grep the output. The detector returns 0 findings on the
clean case and 1+ findings on every other case.
"""

from __future__ import annotations

from detector import detect_duplicate_reference_definitions, format_report


CASES: dict[str, str] = {
    "01-clean-no-duplicates": (
        "See the [docs][docs] and the [api][api].\n"
        "\n"
        "[docs]: https://example.invalid/docs\n"
        "[api]: https://example.invalid/api\n"
    ),
    "02-exact-duplicate-redundant": (
        "Read the [guide][guide].\n"
        "\n"
        "[guide]: https://example.invalid/guide\n"
        "[guide]: https://example.invalid/guide\n"
    ),
    "03-conflicting-url-silent-divergence": (
        "First section talks about the [api][api].\n"
        "Later section also talks about the [api][api], but the\n"
        "regenerated paragraph dropped a fresh definition.\n"
        "\n"
        "[api]: https://example.invalid/api/v1\n"
        "\n"
        "...some intermediate prose...\n"
        "\n"
        "[api]: https://example.invalid/api/v2\n"
    ),
    "04-case-and-whitespace-fold": (
        "See [the docs][The   Docs] and the same [docs][docs].\n"
        "\n"
        "[The   Docs]: https://example.invalid/a\n"
        "[the docs]: https://example.invalid/b\n"
        "[THE DOCS]: https://example.invalid/c\n"
    ),
    "05-conflicting-title-only": (
        "Hover for [tooltip behavior][tip].\n"
        "\n"
        "[tip]: https://example.invalid/tip \"first hover text\"\n"
        "[tip]: https://example.invalid/tip \"second hover text\"\n"
    ),
    "06-fenced-code-is-ignored": (
        "Real definition:\n"
        "\n"
        "[ref]: https://example.invalid/real\n"
        "\n"
        "And here is some sample markdown inside a fence — must not\n"
        "trigger a duplicate finding even though it looks like one:\n"
        "\n"
        "```markdown\n"
        "[ref]: https://example.invalid/in-the-fence\n"
        "[ref]: https://example.invalid/also-in-the-fence\n"
        "```\n"
    ),
    "07-tilde-fence-and-indented-code-are-ignored": (
        "[lib]: https://example.invalid/lib\n"
        "\n"
        "~~~text\n"
        "[lib]: https://example.invalid/inside-tilde-fence\n"
        "~~~\n"
        "\n"
        "Indented code block (4-space lead) — also ignored:\n"
        "\n"
        "    [lib]: https://example.invalid/inside-indented-code\n"
    ),
    "08-multiple-distinct-collisions-in-one-doc": (
        "Refs all over: [a][a], [b][b], [c][c].\n"
        "\n"
        "[a]: https://example.invalid/a-one\n"
        "[b]: https://example.invalid/b-one\n"
        "[c]: https://example.invalid/c-one\n"
        "\n"
        "...refactor pass added these later...\n"
        "\n"
        "[a]: https://example.invalid/a-two\n"
        "[b]: https://example.invalid/b-one\n"
        "[c]: https://example.invalid/c-one \"new title\"\n"
    ),
}


def main() -> None:
    for name, text in CASES.items():
        print(f"=== {name} ===")
        findings = detect_duplicate_reference_definitions(text)
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()

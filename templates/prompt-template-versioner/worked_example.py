"""Worked example: register a few prompt templates across versions,
resolve them with various specifiers, demonstrate fallback chains
and missing-variable behavior.

Run: python3 worked_example.py
"""
from __future__ import annotations

from versioner import (
    TemplateNotFound,
    TemplateRegistry,
    format_version,
    resolve,
    resolve_with_fallback,
)


def section(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def main() -> None:
    reg = TemplateRegistry()

    # Register three "code-review" prompt versions.
    # 1.0.0 -> initial
    # 1.1.0 -> added "cite line numbers"
    # 1.1.1 -> patch: clarified citation format
    # 2.0.0 -> breaking: switched to JSON output
    reg.register(
        "code-review", "1.0.0",
        "Review this diff and report issues:\n$diff",
    )
    reg.register(
        "code-review", "1.1.0",
        "Review this diff and report issues. Cite line numbers.\n$diff",
    )
    reg.register(
        "code-review", "1.1.1",
        "Review this diff and report issues. Cite line numbers as "
        "`file:line`.\n$diff",
    )
    reg.register(
        "code-review", "2.0.0",
        'Review this diff. Output JSON: {"issues": [...]}.\nDIFF:\n$diff',
    )

    # And a "summarize" template only at 0.x — useful for showing the
    # "do NOT silently fall through to 0.x" guardrail later.
    reg.register(
        "summarize", "0.3.0",
        "Summarize the following in <=3 sentences:\n$text",
    )

    section("1. Registered templates")
    for name in reg.names():
        vs = [format_version(v) for v in reg.all_versions(name)]
        print(f"  {name:14s}  versions: {vs}")

    section("2. Exact pin: code-review 1.1.0")
    t = resolve(reg, "code-review", "1.1.0")
    print(f"  matched: {format_version(t.version)}")
    print(f"  body:    {t.body!r}")

    section("3. Floating minor: code-review 1.1 (latest patch)")
    t = resolve(reg, "code-review", "1.1")
    print(f"  matched: {format_version(t.version)}  "
          f"(expected 1.1.1 — latest patch in 1.1)")

    section("4. Floating major: code-review 1 (latest 1.x)")
    t = resolve(reg, "code-review", "1")
    print(f"  matched: {format_version(t.version)}  "
          f"(expected 1.1.1 — latest in 1.x, NOT 2.0.0)")

    section("5. Absolute latest")
    t = resolve(reg, "code-review", "latest")
    print(f"  matched: {format_version(t.version)}  "
          f"(expected 2.0.0)")

    section("6. Fallback chain: prefer 3.x, accept 2.x, refuse 1.x or older")
    res = resolve_with_fallback(reg, "code-review", ["3", "2"])
    print(f"  matched: {format_version(res.matched_version)}")
    print(f"  fell_back_from: {res.fell_back_from}  "
          f"(3.x not registered, 2.x found)")

    section("7. Fallback chain that refuses to silently drop majors")
    # We want 5.x; if not, 4.x; never 3.x or lower. Nothing matches.
    try:
        resolve_with_fallback(reg, "code-review", ["5", "4"])
    except TemplateNotFound as e:
        print(f"  raised: TemplateNotFound: {e}")

    section("8. Render: missing variable raises (no silent empty string)")
    res = resolve_with_fallback(reg, "code-review", ["1"])
    try:
        res.render({"wrong_var": "xyz"})
    except KeyError as e:
        print(f"  raised: KeyError: {e}  "
              f"(template typo never silently emits an empty string)")

    section("9. Render: success")
    out = res.render({"diff": "--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@"})
    print(out)

    section("10. Unknown template")
    try:
        resolve(reg, "does-not-exist", "1")
    except TemplateNotFound as e:
        print(f"  raised: TemplateNotFound: {e}")


if __name__ == "__main__":
    main()

"""Worked example for the image-alt-text presence validator."""

from __future__ import annotations

from validator import format_report, validate_image_alt_text

CASES = {
    "01-clean-informative-alt": (
        "See the deployment topology:\n"
        "\n"
        "![Three-region active-active deployment with primary in us-east-1](https://example.invalid/topology.png)\n"
    ),
    "02-empty-alt": (
        "Architecture sketch below.\n"
        "\n"
        "![](https://example.invalid/arch.png)\n"
    ),
    "03-placeholder-alt": (
        "First diagram:\n"
        "\n"
        "![image](https://example.invalid/one.png)\n"
        "\n"
        "Second diagram:\n"
        "\n"
        "![Screenshot](https://example.invalid/two.png)\n"
    ),
    "04-filename-as-alt": (
        "Reference: ![diagram.png](https://example.invalid/assets/diagram.png)\n"
        "\n"
        "Other:    ![chart](https://example.invalid/assets/chart.png)\n"
    ),
    "05-fenced-code-is-ignored": (
        "Inside a code fence the image syntax is literal text:\n"
        "\n"
        "```\n"
        "![](this-is-not-a-real-image.png)\n"
        "```\n"
        "\n"
        "Real image with good alt:\n"
        "\n"
        "![Latency p99 over 24h, peaking at 410ms during 14:00 UTC](https://example.invalid/p99.png)\n"
    ),
    "06-multiple-images-one-line": (
        "Compare ![](https://example.invalid/a.png) versus ![image](https://example.invalid/b.png) versus ![Throughput in req/s grouped by tenant](https://example.invalid/c.png).\n"
    ),
}


def main() -> None:
    for name in sorted(CASES):
        text = CASES[name]
        findings = validate_image_alt_text(text)
        print(f"=== {name} ===")
        print(format_report(findings))
        print()


if __name__ == "__main__":
    main()

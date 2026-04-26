"""Worked-example cases for `llm-output-sentence-length-outlier-detector`.

Run: `python3 example.py`
"""

from __future__ import annotations

from detector import detect_sentence_length_outliers, format_report


CASES = [
    (
        "01-clean-uniform-paragraph",
        # Five sentences, each 8-15 words. Nothing fires.
        "The build finished in nine minutes flat. The cache hit rate was high. "
        "We saw two flaky tests that retried successfully. The deploy step ran "
        "without incident. Monitoring stayed green for the full hour.\n",
        {},
    ),
    (
        "02-long-sentence-absolute",
        # One sentence well over the default 40-word ceiling.
        "The migration plan involves reading every record from the legacy table, "
        "transforming each field according to the new schema specification, "
        "writing the transformed record into the staging table for verification, "
        "and finally promoting the verified records into the production table "
        "in batches of one thousand to keep the replication lag bounded.\n",
        {},
    ),
    (
        "03-short-sentence-fragment",
        # Single-word "Done." that is a botched stream join.
        "We rolled the patch out to the canary fleet. Done. Then we waited for "
        "the alert window to clear before promoting to general availability.\n",
        {},
    ),
    (
        "04-statistical-outlier-with-tighter-factor",
        # Surrounding sentences are 2-4 words; one is ~30. Absolute check
        # passes (30 < max_words=40), but with `outlier_factor=2.0` the
        # 30-word sentence stands out as a paragraph-relative outlier.
        "We shipped it. Tests stayed green. The dashboard looked clean. "
        "Cache hits rose. Latency held. Then a long sentence appeared describing "
        "the seven distinct steps the on-call engineer took to verify the rollout "
        "across each region one by one in order. Then back to short.\n",
        {"outlier_factor": 2.0},
    ),
    (
        "05-abbreviation-not-a-sentence-boundary",
        # "Dr. Smith arrived." is ONE sentence, not two — so word_count=3
        # for the whole thing, NOT short_sentence on each fragment.
        "Dr. Smith arrived. The Inc. filed Form No. 12 yesterday. "
        "Status: e.g. green, i.e. nominal, etc. The team agreed.\n",
        {},
    ),
    (
        "06-decimal-not-a-sentence-boundary",
        # "3.14" must not split into "3" and "14"-starting sentences.
        "Pi is roughly 3.14 today. The version bumped to 2.0.1 overnight. "
        "We saw 99.95 percent uptime.\n",
        {},
    ),
    (
        "07-code-spans-and-fences-excluded",
        # The fenced Python block contains many `.` chars; the inline
        # `os.path.join` also has dots. NEITHER should add fake sentences
        # or affect word counts.
        "Use `os.path.join` to build paths. Then call `f.write(buf)` and close.\n"
        "```python\n"
        "x = 1.0\n"
        "y = 2.0\n"
        "z = x + y\n"
        "print(z)\n"
        "```\n"
        "After the fence, two short sentences. Then we move on.\n",
        {},
    ),
    (
        "08-permissive-thresholds",
        # Same input as case 02 with max_words=80 — long sentence is allowed.
        "The migration plan involves reading every record from the legacy table, "
        "transforming each field according to the new schema specification, "
        "writing the transformed record into the staging table for verification, "
        "and finally promoting the verified records into the production table "
        "in batches of one thousand to keep the replication lag bounded.\n",
        {"max_words": 80},
    ),
    (
        "09-empty-input",
        "",
        {},
    ),
    (
        "10-single-sentence-no-outlier-possible",
        # Only one sentence; no paragraph stddev possible. No findings
        # (assuming it falls in the absolute window).
        "A single short sentence stands alone here today.\n",
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
        findings = detect_sentence_length_outliers(text, **kwargs)
        print(format_report(findings))


if __name__ == "__main__":
    main()
